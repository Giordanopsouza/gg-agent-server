"""Run with GG_RUNTIME_DATABASE_URL pointed at local Supabase Postgres."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from gg.runtime.ledger import TaskLedger
from gg.runtime.postgres import RuntimePostgres
from gg.runtime.storage import StorageLimits, run_retention_pass
from gg.sdk.domain import Event, EventKind, MessageDeliveryStatus, MessageReceipt
from gg.sdk.task_execution import AgentOutcome, CheckOutcome
from gg.sdk.tasks import TaskState


@pytest.fixture
def local_database():
    url = os.getenv("GG_RUNTIME_DATABASE_URL", "")
    if urlsplit(url).hostname not in {"127.0.0.1", "localhost"}:
        pytest.skip("requires a local Postgres URL")
    database = replace(
        RuntimePostgres.from_env(),
        schema=os.getenv("GG_RUNTIME_TEST_SCHEMA", "runtime_private"),
    )
    with psycopg.connect(database.url, **database.connection_kwargs()) as conn:
        existing = conn.execute(
            sql.SQL("SELECT count(*) FROM {}.tasks").format(
                sql.Identifier(database.schema)
            )
        ).fetchone()
        if existing and existing[0]:
            pytest.skip("requires an empty local runtime tasks table")
    owned: set[str] = set()
    yield database, owned
    if owned:
        with psycopg.connect(database.url, **database.connection_kwargs()) as conn:
            tables = (
                "sandbox_creations",
                "task_reservations",
                "publication_intents",
                "task_supervisions",
                "task_event_copies",
                "task_message_receipts",
                "task_results",
                "retention_tombstones",
            )
            for table in tables:
                conn.execute(
                    sql.SQL("DELETE FROM {}.{} WHERE task_id = ANY(%s)").format(
                        sql.Identifier(database.schema), sql.Identifier(table)
                    ),
                    (list(owned),),
                )
            conn.execute(
                sql.SQL("DELETE FROM {}.tasks WHERE id = ANY(%s)").format(
                    sql.Identifier(database.schema)
                ),
                (list(owned),),
            )


def _submit(ledger: TaskLedger, key: str):
    return ledger.submit(
        idempotency_key=key,
        repository="owner/repo",
        prompt="test task",
        base_ref="main",
        retry_of=None,
    )


def test_cross_connection_admission_claim_and_restart(local_database) -> None:
    database, owned = local_database
    prefix = str(uuid4())

    def submit(index: int):
        with TaskLedger(database) as ledger:
            return _submit(ledger, f"{prefix}-{index % 3}")

    with ThreadPoolExecutor(max_workers=6) as workers:
        submissions = list(workers.map(submit, range(12)))
    owned.update(record.id for record, _ in submissions)
    assert len(owned) == 3
    assert sum(created for _, created in submissions) == 3
    assert len({record.seq for record, _ in submissions}) == 3

    def claim(_: int):
        with TaskLedger(database) as ledger:
            return ledger.reserve_next(capacity=2)

    with ThreadPoolExecutor(max_workers=4) as workers:
        claimed = list(workers.map(claim, range(4)))
    ids = [record.id for record in claimed if record is not None]
    assert len(ids) == len(set(ids)) == 2
    with TaskLedger(database) as restarted:
        assert owned <= {record.id for record in restarted.list()}
        assert {record.task_id for record in restarted.list_reservations()} == set(ids)


def test_crash_rollback_and_durable_evidence(local_database) -> None:
    database, owned = local_database
    with TaskLedger(database) as ledger:
        task, _ = _submit(ledger, str(uuid4()))
        owned.add(task.id)
        assert ledger._conn is not None
        ledger._begin_write()
        ledger._conn.execute(
            "INSERT INTO task_reservations "
            "(task_id, phase, reserved_at, updated_at) VALUES (%s, %s, %s, %s)",
            (
                task.id,
                "starting",
                task.created_at.isoformat(),
                task.created_at.isoformat(),
            ),
        )
        # A connection drop rolls back the uncommitted reservation and lock.
    with TaskLedger(database) as recovered:
        assert recovered.get_reservation(task.id) is None
        assert recovered.reserve_next(capacity=1).id == task.id
        assert (
            recovered.copy_task_event(
                task_id=task.id,
                source_id="execution",
                source_seq=1,
                event=Event(seq=1, kind=EventKind.STATUS, payload={"detail": "done"}),
            )
            == 1
        )
        recovered.archive_task_result(
            task_id=task.id,
            execution_id="execution",
            manifest=None,
            evidence_complete=True,
            evidence_detail=None,
        )
        _, created = recovered.begin_publication(
            task_id=task.id,
            repository="owner/repo",
            task_branch="gg/task",
            base_ref="main",
            task_marker="task-marker",
            commit_sha=None,
            check_outcome=CheckOutcome.NOT_RUN,
            agent_outcome=AgentOutcome.SUCCEEDED,
        )
        assert created
    with TaskLedger(database) as restarted:
        assert len(restarted.list_task_events(task.id)) == 1
        assert restarted.get_task_result(task.id).evidence_complete
        assert restarted.get_publication(task.id) is not None
        _, created = restarted.begin_publication(
            task_id=task.id,
            repository="owner/repo",
            task_branch="gg/task",
            base_ref="main",
            task_marker="task-marker",
            commit_sha=None,
            check_outcome=CheckOutcome.NOT_RUN,
            agent_outcome=AgentOutcome.SUCCEEDED,
        )
        assert not created


def test_receipts_and_retention_preserve_idempotency(local_database) -> None:
    database, owned = local_database
    key = str(uuid4())
    with TaskLedger(database) as ledger:
        task, _ = _submit(ledger, key)
        owned.add(task.id)
        receipt = MessageReceipt(
            id="message-1", content="continue", status=MessageDeliveryStatus.ACCEPTED
        )
        ledger.save_task_message_receipt(task.id, receipt)
        ledger.save_task_message_receipt(task.id, receipt)
        assert len(ledger.list_accepted_task_messages(task.id)) == 1
        ledger.copy_task_event(
            task_id=task.id,
            source_id="execution",
            source_seq=1,
            event=Event(seq=1, kind=EventKind.STATUS, payload={"text": "saved"}),
        )
        ledger.finish_task(task.id, state=TaskState.COMPLETED)
        assert ledger._conn is not None
        ledger._conn.execute(
            "UPDATE tasks SET updated_at = %s WHERE id = %s",
            ((datetime.now(UTC) - timedelta(days=8)).isoformat(), task.id),
        )
        limits = StorageLimits(
            terminal_retention=timedelta(days=7),
            tombstone_retention=timedelta(days=90),
            max_log_evidence_bytes=1024,
            max_artifact_bytes=1024,
            max_total_evidence_bytes=1024 * 1024,
            min_free_disk_bytes=0,
            evidence_dir=None,
        )
        assert run_retention_pass(ledger, limits)[0] == 1
        assert ledger.count_task_log_bytes(task.id) == 0
        replay, created = _submit(ledger, key)
        assert not created and replay.id == task.id and replay.payload_expired
