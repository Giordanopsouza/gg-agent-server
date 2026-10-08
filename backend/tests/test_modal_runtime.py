"""Restore/Volume barriers and graceful drain at the actual runtime surface."""

import asyncio
import sqlite3

import pytest
from fastapi.testclient import TestClient

from gg.runtime.checkpoints import validate_snapshot
from gg.runtime.db_cli import main as db_main
from gg.runtime.modal_runtime import restored_app
from gg.runtime.sqlite_migrations import InvalidDatabase


@pytest.fixture
def state(tmp_path, monkeypatch):
    snapshot = tmp_path / "runtime.snapshot"
    db_main(["init", "--db", str(tmp_path / "seed.db"), "--snapshot", str(snapshot)])
    monkeypatch.setenv("GG_RUNTIME_API_KEY", "operator")
    monkeypatch.setenv("GG_DISPATCH_LOCK_PATH", str(tmp_path / "dispatch.lock"))
    return snapshot, tmp_path / "active.db"


def test_restores_before_serving_and_commits_before_confirmation(state):
    snapshot, local = state
    commits = []

    async def commit():
        commits.append(validate_snapshot(snapshot))

    app = restored_app(snapshot, local, commit)
    assert local.exists() and not hasattr(app.state, "task_ledger")
    with TestClient(app) as client:
        response = client.post(
            "/tasks",
            headers={"X-API-Key": "operator"},
            json={"prompt": "hello", "idempotency_key": "durable"},
        )
        assert response.status_code == 201
        identity = response.json()["id"]
        with sqlite3.connect(snapshot) as db:
            assert db.execute("SELECT id FROM tasks WHERE id=?", (identity,)).fetchone()
        assert app.state.checkpoints.commit is commit
    assert app.state.task_ledger.db._closed
    restarted = restored_app(snapshot, local.with_name("restart.db"), commit)
    with TestClient(restarted) as client:
        assert (
            client.get(
                "/tasks/" + identity, headers={"X-API-Key": "operator"}
            ).status_code
            == 200
        )


def test_missing_corrupt_and_existing_state_fail_closed(state):
    snapshot, local = state

    async def commit():
        pass

    with pytest.raises(FileNotFoundError):
        restored_app(snapshot.with_name("missing"), local, commit)
    snapshot.write_bytes(b"corrupt")
    with pytest.raises(InvalidDatabase):
        restored_app(snapshot, local, commit)
    assert not local.exists()


def test_background_dirty_checkpoint_and_final_shutdown(state):
    snapshot, local = state
    commits = []

    async def commit():
        commits.append(validate_snapshot(snapshot))

    app = restored_app(snapshot, local, commit)
    with TestClient(app) as client:
        ledger = app.state.task_ledger
        ledger.submit(
            prompt="background",
            idempotency_key="background",
            repository=None,
            base_ref=None,
            retry_of=None,
        )
        revision = ledger.db.revision

        async def wait():
            for _ in range(35):
                if app.state.checkpoints.confirmed_revision >= revision:
                    return
                await asyncio.sleep(0.1)
            raise AssertionError("dirty revision was not checkpointed")

        client.portal.call(wait)
        ledger.submit(
            prompt="shutdown",
            idempotency_key="shutdown",
            repository=None,
            base_ref=None,
            retry_of=None,
        )
        final = ledger.db.revision
    assert commits[-1] >= final
