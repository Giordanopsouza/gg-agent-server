"""File-backed admission demo with independent concurrent writers."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest

from gg.runtime.ledger import ReservationPhase, TaskLedger
from gg.runtime.sqlite_db import SQLiteDB, connect, initialize
from gg.runtime.sqlite_migrations import (
    MIGRATIONS,
    SCHEMA_VERSION,
    InvalidDatabase,
    apply_migrations,
)
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


def test_owner_namespaces_and_restart(db):
    ledger = TaskLedger(db)
    owners = [uuid4(), uuid4(), None]
    tasks = [submit(ledger, owner=owner)[0] for owner in owners]
    assert len({task.id for task in tasks}) == 3
    assert [task.seq for task in tasks] == [1, 2, 3]
    assert ledger.get(tasks[0].id, owner_id=owners[1]) is None
    assert [task.id for task in ledger.list(owner_id=owners[0])] == [tasks[0].id]
    db.close()
    with SQLiteDB(db.path) as reopened:
        ledger = TaskLedger(reopened)
        for owner, task in zip(owners, tasks):
            replay, created = submit(ledger, owner=owner)
            assert not created and replay == task
            assert task.owner_id == owner
            assert task.created_at.tzinfo is not None
            assert task.repository is None and task.base_sha is None
        assert [t.id for t in ledger.list()] == [t.id for t in tasks]
        assert submit(ledger, "next")[0].seq == 4


def test_duplicate_submission_race_across_connections(db):
    owner = uuid4()

    def write(_):
        with SQLiteDB(db.path) as other:
            return submit(TaskLedger(other), owner=owner)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(write, range(24)))
    assert sum(created for _, created in results) == 1
    assert len({task.id for task, _ in results}) == 1
    assert submit(TaskLedger(db), "new")[0].seq == 2


def test_concurrent_reservations_capacity_fifo_and_restart(db):
    ledger = TaskLedger(db)
    tasks = [submit(ledger, str(i))[0] for i in range(18)]
    barrier = Barrier(18)

    def reserve(_):
        with SQLiteDB(db.path) as other:
            barrier.wait(timeout=10)
            return TaskLedger(other).reserve_next(capacity=10)

    with ThreadPoolExecutor(max_workers=18) as pool:
        results = list(pool.map(reserve, range(18)))
    reserved = [r for r in results if r]
    assert sorted(t.seq for t in reserved) == list(range(1, 11))
    assert len(ledger.list_reservations()) == 10
    assert all(t.state is TaskState.STARTING for t in reserved)
    db.close()
    with SQLiteDB(db.path) as reopened:
        ledger = TaskLedger(reopened)
        assert ledger.reserve_next(capacity=10) is None
        ledger.update_reservation(
            tasks[0].id, phase=ReservationPhase.RUNNING, task_state=TaskState.RUNNING
        )
        ledger.release_reservation(tasks[0].id)
        assert ledger.get(tasks[0].id).sandbox_cleanup_status == "confirmed_absent"
        assert ledger.reserve_next(capacity=10).seq == 11


@pytest.mark.parametrize("capacity", [0, -1, 11])
def test_invalid_capacity(db, capacity):
    with pytest.raises(ValueError):
        TaskLedger(db).reserve_next(capacity=capacity)


def test_reservation_partial_write_rolls_back(db):
    ledger = TaskLedger(db)
    task, _ = submit(ledger)
    with db.write() as tx:
        tx.connection.execute(
            """
            CREATE TRIGGER reject_state BEFORE UPDATE OF state ON tasks BEGIN
            SELECT RAISE(ABORT, 'injected failure'); END
            """
        )
    revision = db.revision
    with pytest.raises(sqlite3.IntegrityError, match="injected"):
        ledger.reserve_next(capacity=10)
    assert db.revision == revision
    assert ledger.get(task.id).state is TaskState.QUEUED
    assert ledger.list_reservations() == []


def test_upgrade_version_one_and_corrupt_schema(tmp_path):
    path = tmp_path / "old.db"
    connection = sqlite3.connect(path, isolation_level=None)
    apply_migrations(connection, MIGRATIONS[:1])
    connection.close()
    connection = connect(path)
    apply_migrations(connection)
    assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    connection.close()
    with SQLiteDB(path) as database:
        assert database.revision == SCHEMA_VERSION - 1
        assert submit(TaskLedger(database))[0].seq == 1
    connection = connect(path)
    connection.execute("DROP INDEX tasks_owner_key")
    connection.close()
    with pytest.raises(InvalidDatabase, match="schema"):
        SQLiteDB(path)
