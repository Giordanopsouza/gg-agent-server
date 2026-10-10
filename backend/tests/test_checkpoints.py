"""Checkpoint barriers under writes, commit failures and cancellation."""

import asyncio
import sqlite3

import pytest

from gg.runtime.checkpoints import (
    CheckpointCoordinator,
    publish_snapshot,
    validate_snapshot,
)
from gg.runtime.sqlite_db import SQLiteDB, initialize


def write(db, value):
    with db.write() as tx:
        tx.connection.execute("INSERT INTO demo VALUES (?)", (value,))
    return tx.revision


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "db"
    initialize(path)
    with SQLiteDB(path) as db:
        with db.write() as tx:
            tx.connection.execute("CREATE TABLE demo (value TEXT)")
        yield db


def test_write_during_commit_requires_another_checkpoint(db, tmp_path):
    async def demo():
        entered, release = asyncio.Event(), asyncio.Event()
        commits = 0

        async def commit():
            nonlocal commits
            commits += 1
            entered.set()
            await release.wait()

        snapshot = tmp_path / "snapshot"
        coordinator = CheckpointCoordinator(db, snapshot, commit)
        first = write(db, "first")
        checkpoint = asyncio.create_task(coordinator.checkpoint())
        await entered.wait()
        assert validate_snapshot(snapshot) == first
        second = write(db, "second")
        waiter = asyncio.create_task(coordinator.wait_until_confirmed(second))
        await asyncio.sleep(0)
        release.set()
        assert await checkpoint == first
        assert coordinator.confirmed_revision == first
        assert coordinator.pending and not waiter.done()
        await coordinator.ensure_durable(second)
        await asyncio.wait_for(waiter, 1)
        assert commits == 2 and not coordinator.pending
        connection = sqlite3.connect(snapshot)
        try:
            assert connection.execute("SELECT value FROM demo").fetchall() == [
                ("first",),
                ("second",),
            ]
        finally:
            connection.close()

    asyncio.run(demo())


def test_commit_failure_preserves_local_data_and_waiters(db, tmp_path):
    async def demo():
        fail = True

        async def commit():
            if fail:
                raise OSError("Volume unavailable")

        revision = write(db, "pending")
        coordinator = CheckpointCoordinator(db, tmp_path / "snapshot", commit)
        waiter = asyncio.create_task(coordinator.wait_until_confirmed(revision))
        with pytest.raises(OSError):
            await coordinator.ensure_durable(revision)
        assert coordinator.confirmed_revision == -1 and coordinator.pending
        assert not waiter.done() and db.revision == revision
        fail = False
        await coordinator.ensure_durable(revision)
        await asyncio.wait_for(waiter, 1)
        with pytest.raises(ValueError):
            await coordinator.ensure_durable(revision + 1)

    asyncio.run(demo())


def test_cancelled_checkpoint_keeps_commit_serialized_and_unconfirmed(db, tmp_path):
    async def demo():
        entered, release = asyncio.Event(), asyncio.Event()
        calls = 0

        async def commit():
            nonlocal calls
            calls += 1
            entered.set()
            await release.wait()

        coordinator = CheckpointCoordinator(db, tmp_path / "snapshot", commit)
        revision = write(db, "pending")
        waiter = asyncio.create_task(coordinator.wait_until_confirmed(revision))
        checkpoint = asyncio.create_task(coordinator.checkpoint())
        await entered.wait()
        checkpoint.cancel()
        retry = asyncio.create_task(coordinator.ensure_durable(revision))
        await asyncio.sleep(0)
        assert calls == 1 and not waiter.done()
        checkpoint.cancel()  # Repeated cancellation must not cancel the commit.
        await asyncio.sleep(0)
        assert calls == 1 and not checkpoint.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await checkpoint
        await retry
        await asyncio.wait_for(waiter, 1)
        assert calls == 2 and coordinator.confirmed_revision == revision

    asyncio.run(demo())


def test_snapshot_failure_does_not_call_commit(db, tmp_path, monkeypatch):
    async def demo():
        calls = 0

        async def commit():
            nonlocal calls
            calls += 1

        coordinator = CheckpointCoordinator(db, tmp_path / "snapshot", commit)

        def fail(*args):
            raise OSError("disk full")

        monkeypatch.setattr("gg.runtime.checkpoints.publish_snapshot", fail)
        with pytest.raises(OSError):
            await coordinator.checkpoint()
        assert calls == 0 and coordinator.confirmed_revision == -1

    asyncio.run(demo())


def test_snapshot_cannot_replace_active_database(db):
    with pytest.raises(ValueError):
        publish_snapshot(db, db.path)
    assert db.revision == 1


def test_cancel_without_retry_does_not_confirm_or_release_waiter(db, tmp_path):
    async def demo():
        entered, release = asyncio.Event(), asyncio.Event()

        async def commit():
            entered.set()
            await release.wait()

        coordinator = CheckpointCoordinator(db, tmp_path / "snapshot", commit)
        revision = write(db, "pending")
        waiter = asyncio.create_task(coordinator.wait_until_confirmed(revision))
        checkpoint = asyncio.create_task(coordinator.checkpoint())
        await entered.wait()
        checkpoint.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await checkpoint
        assert coordinator.confirmed_revision == -1 and coordinator.pending
        assert not waiter.done()
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter

    asyncio.run(demo())


def test_checkpoint_calls_are_serialized(db, tmp_path):
    async def demo():
        active = maximum = calls = 0

        async def commit():
            nonlocal active, maximum, calls
            calls += 1
            active += 1
            maximum = max(maximum, active)
            await asyncio.sleep(0.01)
            active -= 1

        coordinator = CheckpointCoordinator(db, tmp_path / "snapshot", commit)
        await asyncio.gather(*(coordinator.checkpoint() for _ in range(4)))
        assert calls == 4 and maximum == 1

    asyncio.run(demo())


def test_failed_publication_preserves_previous_snapshot(db, tmp_path, monkeypatch):
    snapshot = tmp_path / "snapshot"
    publish_snapshot(db, snapshot)
    original = snapshot.read_bytes()
    write(db, "pending")

    def fail(*args):
        raise OSError("rename failed")

    monkeypatch.setattr("gg.runtime.checkpoints.os.replace", fail)
    with pytest.raises(OSError, match="rename failed"):
        publish_snapshot(db, snapshot)
    assert snapshot.read_bytes() == original
    assert not list(tmp_path.glob(".snapshot-*"))
    assert db.revision == 2


@pytest.mark.parametrize("suffix", ["-wal", "-shm", "-journal", ".lock"])
def test_snapshot_cannot_replace_active_sidecars(db, suffix):
    with pytest.raises(ValueError):
        publish_snapshot(db, db.path.with_name(db.path.name + suffix))
    assert db.revision == 1


def test_revision_waiters_coalesce_after_acquiring_lock(db, tmp_path):
    async def demo():
        calls = 0
        entered, release = asyncio.Event(), asyncio.Event()

        async def commit():
            nonlocal calls
            calls += 1
            entered.set()
            await release.wait()

        coordinator = CheckpointCoordinator(db, tmp_path / "snapshot", commit)
        revision = write(db, "first")
        waiters = [
            asyncio.create_task(coordinator.ensure_durable(revision)) for _ in range(4)
        ]
        await entered.wait()
        newer = write(db, "during commit")
        release.set()
        await asyncio.gather(*waiters)
        assert calls == 1 and coordinator.confirmed_revision == revision
        await coordinator.ensure_durable(newer)
        assert calls == 2 and coordinator.confirmed_revision == newer
        await coordinator.checkpoint()  # Explicit publication still commits.
        assert calls == 3

    asyncio.run(demo())


def test_concurrent_revision_waiters_retry_failed_commit(db, tmp_path):
    async def demo():
        calls = 0

        async def commit():
            nonlocal calls
            calls += 1
            await asyncio.sleep(0)
            if calls == 1:
                raise OSError("unavailable")

        coordinator = CheckpointCoordinator(db, tmp_path / "snapshot", commit)
        revision = write(db, "pending")
        results = await asyncio.gather(
            *(coordinator.ensure_durable(revision) for _ in range(4)),
            return_exceptions=True,
        )
        assert sum(isinstance(result, OSError) for result in results) == 1
        assert calls == 2 and coordinator.confirmed_revision == revision
        assert coordinator.last_error is None

    asyncio.run(demo())
