"""Offline identity, session durability, revocation and snapshot recovery."""

import asyncio
import shutil
import time
from uuid import UUID

import pytest
from fastapi import HTTPException

from gg.runtime.checkpoints import CheckpointCoordinator
from gg.runtime.local_sessions import SESSION_SECONDS, LocalSessions, token_hash
from gg.runtime.sqlite_db import SQLiteDB, initialize


@pytest.mark.anyio
async def test_sub_identity_is_stable_and_tokens_are_only_hashed(tmp_path):
    path = tmp_path / "db"
    initialize(path)

    async def commit():
        pass

    with SQLiteDB(path) as db:
        checkpoints = CheckpointCoordinator(db, tmp_path / "snapshot", commit)
        sessions = LocalSessions(db, checkpoints)
        first = await sessions.create("google-a", "old@example.com")
        owner = (await sessions.user(first))["id"]
        assert UUID(owner)
        second = await sessions.create("google-a", "new@example.com")
        other = await sessions.create("google-b", "new@example.com")
        assert (await sessions.user(second))["id"] == owner
        assert (await sessions.user(other))["id"] != owner
        assert (await sessions.user(first))["email"] == "new@example.com"
        with db.read() as connection:
            rows = connection.execute("SELECT * FROM local_sessions").fetchall()
            assert first not in str(rows) and second not in str(rows)
            assert rows[0][0] == token_hash(first)
            assert abs(rows[0][2] - int(time.time()) - SESSION_SECONDS) < 5
        await sessions.revoke(first)
        with pytest.raises(HTTPException) as error:
            await sessions.user(first)
        assert error.value.status_code == 401
        with db.write() as tx:
            tx.connection.execute(
                "UPDATE local_sessions SET expires_at = 1 WHERE token_hash = ?",
                (token_hash(second),),
            )
        await checkpoints.ensure_durable(tx.revision)
    shutil.copyfile(tmp_path / "snapshot", tmp_path / "restored")
    with SQLiteDB(tmp_path / "restored") as db:
        sessions = LocalSessions(
            db, CheckpointCoordinator(db, tmp_path / "snapshot2", commit)
        )
        for token in (first, second, "forged"):
            with pytest.raises(HTTPException) as error:
                await sessions.user(token)
            assert error.value.status_code == 401
        assert (await sessions.user(other))["id"] != owner


@pytest.mark.anyio
async def test_mutations_wait_for_commit_and_failed_revoke_is_retryable(tmp_path):
    initialize(tmp_path / "db")
    entered, release = asyncio.Event(), asyncio.Event()
    fail = False

    async def commit():
        entered.set()
        await release.wait()
        if fail:
            raise OSError("private failure")

    with SQLiteDB(tmp_path / "db") as db:
        checkpoints = CheckpointCoordinator(db, tmp_path / "snapshot", commit)
        sessions = LocalSessions(db, checkpoints)
        pending = asyncio.create_task(sessions.create("a", "a@example.com"))
        await entered.wait()
        assert not pending.done()
        release.set()
        token = await pending
        fail = True
        with pytest.raises(HTTPException) as error:
            await sessions.revoke(token)
        assert error.value.status_code == 503
        assert "private" not in str(error.value.detail)
        fail = False
        await sessions.revoke(token)
        with pytest.raises(HTTPException) as error:
            await sessions.user(token)
        assert error.value.status_code == 401


@pytest.mark.anyio
async def test_reads_ignore_unrelated_writes_and_failures_but_not_pending_identity(
    tmp_path,
):
    initialize(tmp_path / "db")
    calls = 0
    fail = False

    async def commit():
        nonlocal calls
        calls += 1
        if fail:
            raise OSError("unavailable")

    with SQLiteDB(tmp_path / "db") as db:
        checkpoints = CheckpointCoordinator(db, tmp_path / "snapshot", commit)
        sessions = LocalSessions(db, checkpoints)
        token = await sessions.create("a", "a@example.com")
        with db.write() as tx:
            tx.connection.execute("CREATE TABLE unrelated (value TEXT)")
        fail = True
        with pytest.raises(OSError):
            await checkpoints.checkpoint()
        before = calls
        users = await asyncio.gather(*(sessions.user(token) for _ in range(4)))
        assert all(user["email"] == "a@example.com" for user in users)
        with pytest.raises(HTTPException) as error:
            await sessions.user("invalid")
        assert error.value.status_code == 401 and calls == before
        with db.write() as tx:
            sessions.insert(tx.connection, "a", "changed@example.com", "pending")
        for candidate in (token, "pending"):
            with pytest.raises(HTTPException) as error:
                await sessions.user(candidate)
            assert error.value.status_code == 503
        fail = False
        assert (await sessions.user("pending"))["email"] == "changed@example.com"
        fail = True
        with pytest.raises(HTTPException):
            await sessions.revoke(token)
        before = calls
        with pytest.raises(HTTPException) as error:
            await sessions.user(token)
        assert error.value.status_code == 401 and calls == before
        with pytest.raises(RuntimeError):
            with db.write() as tx:
                sessions.insert(
                    tx.connection, "a", "rolledback@example.com", "rollback"
                )
                raise RuntimeError("rollback")
        assert (await sessions.user("pending"))["email"] == "changed@example.com"


@pytest.mark.anyio
async def test_revocation_during_session_creation_barrier_is_rechecked(tmp_path):
    initialize(tmp_path / "db")
    entered, release = asyncio.Event(), asyncio.Event()

    async def commit():
        entered.set()
        await release.wait()

    with SQLiteDB(tmp_path / "db") as db:
        checkpoints = CheckpointCoordinator(db, tmp_path / "snapshot", commit)
        sessions = LocalSessions(db, checkpoints)
        with db.write() as tx:
            sessions.insert(tx.connection, "a", "a@example.com", "pending")
        reading = asyncio.create_task(sessions.user("pending"))
        await entered.wait()
        revoking = asyncio.create_task(sessions.revoke("pending"))
        await asyncio.sleep(0)
        release.set()
        with pytest.raises(HTTPException) as error:
            await reading
        assert error.value.status_code == 401
        await revoking
