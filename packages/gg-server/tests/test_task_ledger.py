from __future__ import annotations

import sqlite3
import stat

import pytest

from gg.runtime.ledger import (
    SUPPORTED_SCHEMA_VERSION,
    SandboxProviderState,
    TaskLedger,
)


def _submit(
    ledger: TaskLedger, *, key: str, repo: str = "owner/name", prompt: str = "p"
):
    return ledger.submit(
        idempotency_key=key,
        repository=repo,
        prompt=prompt,
        base_ref=None,
        retry_of=None,
    )


def test_ledger_assigns_monotonic_fifo_sequence(tmp_path) -> None:
    db_path = str(tmp_path / "tasks.sqlite")
    with TaskLedger(db_path=db_path) as ledger:
        first, created_first = _submit(ledger, key="k1")
        second, created_second = _submit(ledger, key="k2")
        third, created_third = _submit(ledger, key="k3")

    assert (created_first, created_second, created_third) == (True, True, True)
    assert [first.seq, second.seq, third.seq] == [1, 2, 3]


def test_ledger_idempotent_replay_returns_same_record(tmp_path) -> None:
    db_path = str(tmp_path / "tasks.sqlite")
    with TaskLedger(db_path=db_path) as ledger:
        original, created = _submit(ledger, key="k1", prompt="do it")
        replay, created_replay = _submit(ledger, key="k1", prompt="do it")

    assert created is True
    assert created_replay is False
    assert replay.id == original.id
    assert replay.seq == original.seq


def test_ledger_persists_across_restart_in_fifo_order(tmp_path) -> None:
    db_path = str(tmp_path / "tasks.sqlite")
    with TaskLedger(db_path=db_path) as ledger:
        _submit(ledger, key="k1")
        _submit(ledger, key="k2")
        _submit(ledger, key="k3")

    # Simulate a process restart: open a fresh ledger over the same file.
    with TaskLedger(db_path=db_path) as restarted:
        records = restarted.list()

    assert [record.idempotency_key for record in records] == ["k1", "k2", "k3"]
    assert [record.seq for record in records] == [1, 2, 3]
    assert all(record.state.value == "queued" for record in records)


def test_ledger_sequence_continues_after_restart(tmp_path) -> None:
    db_path = str(tmp_path / "tasks.sqlite")
    with TaskLedger(db_path=db_path) as ledger:
        _submit(ledger, key="k1")
        _submit(ledger, key="k2")

    with TaskLedger(db_path=db_path) as ledger:
        third, created = _submit(ledger, key="k3")

    assert created is True
    assert third.seq == 3


def test_ledger_rejects_unsupported_future_schema(tmp_path) -> None:
    db_path = str(tmp_path / "tasks.sqlite")
    future = SUPPORTED_SCHEMA_VERSION + 1
    with TaskLedger(db_path=db_path) as ledger:
        _submit(ledger, key="k1")

    # Tamper with the schema version to simulate a future runtime having written it.
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE schema_meta SET value = ? WHERE key = 'schema_version'",
        (str(future),),
    )
    conn.commit()
    conn.close()

    with pytest.raises(RuntimeError, match="unsupported task ledger schema version"):
        TaskLedger(db_path=db_path, schema_version=SUPPORTED_SCHEMA_VERSION).open()


def test_ledger_migrates_v1_to_private_sandbox_intents(tmp_path) -> None:
    db_path = str(tmp_path / "tasks.sqlite")
    with TaskLedger(db_path=db_path, schema_version=1) as old_ledger:
        task, _ = _submit(old_ledger, key="k1")

    with TaskLedger(db_path=db_path) as migrated:
        record, created = migrated.begin_sandbox_creation(
            task_id=task.id,
            deployment="production",
            sandbox_name="gg-production-task",
            tags_json='{"gg_task_id":"task"}',
            session_api_key="private-key",
        )

    assert created is True
    assert record.provider_state.value == "creating"
    assert record.provider_id is None


def test_ledger_migrates_v2_to_capacity_reservations(tmp_path) -> None:
    db_path = str(tmp_path / "tasks.sqlite")
    with TaskLedger(db_path=db_path, schema_version=2) as old_ledger:
        first, _ = _submit(old_ledger, key="k1")
        _submit(old_ledger, key="k2")

    with TaskLedger(db_path=db_path) as migrated:
        claimed = migrated.reserve_next(capacity=1)

    assert claimed is not None
    assert claimed.id == first.id
    assert claimed.state.value == "starting"


def test_v2_migration_backfills_existing_provider_ownership(tmp_path) -> None:
    db_path = str(tmp_path / "tasks.sqlite")
    with TaskLedger(db_path=db_path, schema_version=2) as old_ledger:
        task, _ = _submit(old_ledger, key="k1")
        old_ledger.begin_sandbox_creation(
            task_id=task.id,
            deployment="production",
            sandbox_name="existing-sandbox",
            tags_json="{}",
            session_api_key="private",
        )
        old_ledger.update_sandbox_creation(
            task.id,
            provider_id="provider-id",
            provider_state=SandboxProviderState.RUNNING,
        )

    with TaskLedger(db_path=db_path) as migrated:
        reservation = migrated.get_reservation(task.id)
        public_task = migrated.get(task.id)

    assert reservation is not None
    assert reservation.phase.value == "running"
    assert public_task is not None
    assert public_task.state.value == "running"


def test_ledger_file_is_private_because_it_contains_sandbox_credentials(
    tmp_path,
) -> None:
    db_path = tmp_path / "tasks.sqlite"
    with TaskLedger(db_path=str(db_path)):
        pass

    assert stat.S_IMODE(db_path.stat().st_mode) == 0o600


def test_ledger_get_returns_none_for_unknown_id(tmp_path) -> None:
    with TaskLedger(db_path=":memory:") as ledger:
        assert ledger.get("missing") is None
        record, _ = _submit(ledger, key="k1")
        assert ledger.get(record.id) is not None


def test_ledger_concurrent_duplicate_submissions_insert_once(tmp_path) -> None:
    from concurrent.futures import ThreadPoolExecutor

    db_path = str(tmp_path / "tasks.sqlite")
    ledger = TaskLedger(db_path=db_path)
    ledger.open()

    def submit_one() -> tuple[object, bool]:
        return ledger.submit(
            idempotency_key="race",
            repository="owner/name",
            prompt="same",
            base_ref=None,
            retry_of=None,
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: submit_one(), range(16)))

    ledger.close()

    created_flags = [created for _, created in results]
    ids = {record.id for record, _ in results}
    assert created_flags.count(True) == 1
    assert created_flags.count(False) == 15
    # Every replay returned the same task id.
    assert len(ids) == 1
    # And only one row exists on disk.
    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    conn.close()
    assert count == 1
