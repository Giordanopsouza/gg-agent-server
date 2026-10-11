"""Retention removes payload while compact identities/counters persist."""

import sqlite3
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from gg.runtime.ledger import TaskLedger
from gg.runtime.sqlite_db import SQLiteDB, initialize
from gg.runtime.storage import (
    StorageLimits,
    admission_pressure,
    run_retention_pass,
    truncate_event_json,
    truncate_manifest,
)
from gg.sdk.domain import Event, EventKind, MessageDeliveryStatus, MessageReceipt
from gg.sdk.task_execution import AgentOutcome, TaskResultManifest
from gg.sdk.tasks import TaskState


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "runtime.db"
    initialize(path)
    with SQLiteDB(path) as database:
        yield database


def submit(ledger, key="key", owner=None):
    return ledger.submit(
        idempotency_key=key,
        owner_id=owner,
        repository=None,
        prompt="work ' ; --",
        base_ref=None,
        retry_of=None,
    )


def copy(ledger, task_id, seq=1, source="conversation", **fields):
    event = Event(seq=seq, kind=EventKind.MESSAGE, payload={"text": "ação"})
    return ledger.copy_task_event(
        task_id=task_id, source_id=source, source_seq=seq, event=event, **fields
    )


def limits(**changes):
    return StorageLimits(
        **(
            dict(
                terminal_retention=timedelta(days=1),
                tombstone_retention=timedelta(days=1),
                max_log_evidence_bytes=4096,
                max_artifact_bytes=8192,
                max_total_evidence_bytes=65536,
                min_free_disk_bytes=0,
                evidence_dir=None,
            )
            | changes
        )
    )


def test_dedup_cursor_restart_and_payload_expiry(db):
    ledger = TaskLedger(db)
    task, _ = submit(ledger)
    assert copy(ledger, task.id) == 1
    assert copy(ledger, task.id) is None
    assert copy(ledger, task.id, source="second") == 2
    assert copy(ledger, task.id, seq=2) == 3
    assert [
        cursor for cursor, *_ in ledger.list_task_events(task.id, after_cursor=1)
    ] == [2, 3]
    # Expiring a page independently must never reuse its cursor or source identity.
    with db.write() as tx:
        tx.connection.execute(
            "DELETE FROM task_event_copies WHERE task_id = ?", (task.id,)
        )
    with SQLiteDB(db.path) as reopened:
        ledger = TaskLedger(reopened)
        assert copy(ledger, task.id) is None
        assert copy(ledger, task.id, seq=3) == 4


def test_result_receipts_utf8_bytes_and_storage_limits(db):
    ledger = TaskLedger(db)
    task, _ = submit(ledger)
    copy(ledger, task.id)
    event = ledger.list_task_events(task.id)[0][3]
    receipt = MessageReceipt(
        id="message", content="ação", status=MessageDeliveryStatus.ACCEPTED, detail="é"
    )
    ledger.save_task_message_receipt(task.id, receipt)
    manifest = TaskResultManifest(
        task_id=task.id,
        execution_id="execution",
        patch="a" * 20000,
        agent_outcome=AgentOutcome.SUCCEEDED,
    )
    bounded, truncated = truncate_manifest(manifest, max_bytes=8192)
    assert truncated and bounded.patch_truncated
    ledger.archive_task_result(
        task_id=task.id,
        execution_id="execution",
        manifest=bounded,
        evidence_complete=True,
        evidence_detail=None,
    )
    assert ledger.count_task_log_bytes(task.id) == len(
        event.model_dump_json().encode()
    ) + len("açãoé".encode())
    assert ledger.count_task_artifact_bytes(task.id) == len(
        bounded.model_dump_json().encode()
    )
    assert ledger.count_total_evidence_bytes() == ledger.count_task_log_bytes(
        task.id
    ) + ledger.count_task_artifact_bytes(task.id)
    assert admission_pressure(ledger, limits(max_total_evidence_bytes=1)).blocked
    assert not admission_pressure(ledger, limits()).blocked
    with SQLiteDB(db.path) as reopened:
        ledger = TaskLedger(reopened)
        assert ledger.get_task_result(task.id).manifest == bounded
        assert ledger.list()[0].agent_outcome == "succeeded"
    ledger = TaskLedger(db)
    huge = Event(seq=2, kind=EventKind.MESSAGE, payload={"text": "a" * 50000})
    payload, truncated = truncate_event_json(
        huge, max_task_log_bytes=4096, current_log_bytes=0
    )
    assert truncated and len(payload.encode()) <= 4096
    assert copy(ledger, task.id, seq=2, event_json=payload) == 2


def test_retention_compact_owner_idempotency_after_purge_restart(db):
    ledger = TaskLedger(db)
    owners = [uuid4(), uuid4(), None]
    tasks = [submit(ledger, owner=o)[0] for o in owners]
    for task in tasks:
        copy(ledger, task.id)
        ledger.save_task_message_receipt(
            task.id,
            MessageReceipt(
                id="message",
                content="private payload",
                status=MessageDeliveryStatus.ACCEPTED,
            ),
        )
        ledger.archive_task_result(
            task_id=task.id,
            execution_id="execution",
            manifest=TaskResultManifest(
                task_id=task.id, execution_id="execution", patch="private patch"
            ),
            evidence_complete=True,
            evidence_detail=None,
        )
        ledger.finish_task(task.id, state=TaskState.COMPLETED)
    future = datetime.now(UTC) + timedelta(days=3)
    assert run_retention_pass(ledger, limits(), now=future) == (3, 3)
    assert ledger.list() == [] and ledger.count_total_evidence_bytes() == 0
    assert ledger.get_task_result(tasks[0].id) is None
    assert ledger.get_task_message_receipt(tasks[0].id, "message") is None
    db.close()
    with SQLiteDB(db.path) as reopened:
        ledger = TaskLedger(reopened)
        for task, owner in zip(tasks, owners):
            replay, created = submit(ledger, owner=owner)
            assert not created and replay.id == task.id and replay.seq == task.seq
            assert replay.payload_expired and replay.prompt == ""
            assert copy(ledger, task.id) is None
            with pytest.raises(KeyError):
                copy(ledger, task.id, seq=2)
        assert submit(ledger, "new")[0].seq == 4
        with reopened.read() as connection:
            assert (
                connection.execute("SELECT value FROM ledger_counters").fetchone()[0]
                == 4
            )
            assert (
                connection.execute(
                    "SELECT COUNT(*) FROM task_event_counters"
                ).fetchone()[0]
                == 3
            )
            assert (
                connection.execute("SELECT COUNT(*) FROM task_idempotency").fetchone()[
                    0
                ]
                == 3
            )


def test_retention_protects_reserved_and_sleeping_workspaces(db):
    ledger = TaskLedger(db)
    reserved, _ = submit(ledger)
    ledger.reserve_next(capacity=10)
    ledger.finish_task(reserved.id, state=TaskState.FAILED)
    sleeping, _ = submit(ledger, "sleeping")
    ledger.finish_task(sleeping.id, state=TaskState.SLEEPING)
    copy(ledger, reserved.id)
    copy(ledger, sleeping.id)
    future = datetime.now(UTC) + timedelta(days=3)
    assert run_retention_pass(ledger, limits(), now=future) == (0, 0)
    assert len(ledger.list_task_events(reserved.id)) == 1
    assert len(ledger.list_task_events(sleeping.id)) == 1
    ledger.release_reservation(reserved.id)
    assert run_retention_pass(ledger, limits(), now=future) == (1, 1)


def test_retention_rollback_keeps_payload_and_identity(db):
    ledger = TaskLedger(db)
    task, _ = submit(ledger)
    copy(ledger, task.id)
    ledger.finish_task(task.id, state=TaskState.COMPLETED)
    with db.write() as tx:
        tx.connection.execute(
            """
            CREATE TRIGGER reject_expiry BEFORE UPDATE ON tasks BEGIN SELECT
            RAISE(ABORT, 'injected failure'); END
            """
        )
    revision = db.revision
    with pytest.raises(sqlite3.IntegrityError):
        run_retention_pass(ledger, limits(), now=datetime.now(UTC) + timedelta(days=3))
    assert db.revision == revision
    assert not ledger.get(task.id).payload_expired
    assert len(ledger.list_task_events(task.id)) == 1
    with db.read() as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM task_idempotency").fetchone()[0]
            == 0
        )


def test_remote_effect_is_compact_and_expires(db):
    import json

    from gg.sdk.publication import PublicationState
    from gg.sdk.task_execution import CheckOutcome

    ledger = TaskLedger(db)
    task, _ = submit(ledger)
    ledger.begin_publication(
        task_id=task.id,
        repository="owner/repo",
        task_branch="branch",
        base_ref="main",
        task_marker="marker",
        commit_sha="sha",
        check_outcome=CheckOutcome.PASSED,
        agent_outcome=AgentOutcome.SUCCEEDED,
    )
    ledger.update_publication(
        task.id,
        state=PublicationState.PUBLISHED,
        pr_number=42,
        pr_url="https://github.com/owner/repo/pull/42",
        pr_state="open",
        detail="private bulky payload",
    )
    ledger.finish_task(task.id, state=TaskState.COMPLETED)
    assert (
        ledger.expire_terminal_payloads(
            before=datetime.now(UTC) + timedelta(days=2),
            tombstone_retention=timedelta(days=1),
        )
        == 1
    )
    with db.read() as connection:
        remote = json.loads(
            connection.execute(
                "SELECT remote_effect_json FROM retention_tombstones"
            ).fetchone()[0]
        )
        assert remote == dict(
            pr_number=42,
            pr_url="https://github.com/owner/repo/pull/42",
            pr_state="open",
            state="published",
        )
        assert (
            connection.execute("SELECT COUNT(*) FROM publication_intents").fetchone()[0]
            == 0
        )
    assert (
        ledger.purge_expired_tombstones(before=datetime.now(UTC) + timedelta(days=2))
        == 1
    )
    with db.read() as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM retention_tombstones").fetchone()[
                0
            ]
            == 0
        )


def test_failed_event_copy_rolls_back_identity_and_cursor(db):
    ledger = TaskLedger(db)
    task, _ = submit(ledger)
    revision = db.revision
    with pytest.raises(sqlite3.IntegrityError):
        copy(ledger, task.id, event_json="invalid json")
    assert db.revision == revision
    assert copy(ledger, task.id) == 1
