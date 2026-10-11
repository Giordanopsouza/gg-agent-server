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


def test_active_backup_uses_coordinator_and_requires_operator(state, tmp_path):
    snapshot, local = state
    commits = []

    async def commit():
        commits.append(validate_snapshot(snapshot))

    application = restored_app(snapshot, local, commit)
    with TestClient(application) as client:
        assert client.post("/ops/backup").status_code == 401
        response = client.post("/ops/backup", headers={"X-API-Key": "operator"})
        assert response.status_code == 200
        downloaded = tmp_path / "downloaded.snapshot"
        downloaded.write_bytes(response.content)
        revision = validate_snapshot(downloaded)
        assert int(response.headers["X-Runtime-Revision"]) == revision
        assert revision in commits
        ready = client.get("/ready", headers={"X-API-Key": "operator"}).json()
        assert ready["confirmed_revision"] >= revision
        assert ready["revision"] >= revision
        assert ready["version"] == "local"


def test_backup_commit_failure_is_not_confirmed(state):
    snapshot, local = state
    broken = False

    async def commit():
        if broken:
            raise OSError("unavailable")

    application = restored_app(snapshot, local, commit)
    with TestClient(application) as client:
        broken = True
        response = client.post("/ops/backup", headers={"X-API-Key": "operator"})
        assert response.status_code == 503
        assert application.state.checkpoints.last_error == "OSError"
        broken = False


def test_offline_operations_preserve_initial_and_previous_snapshot(tmp_path):
    from gg.runtime.modal_operations import offline_state

    snapshot = tmp_path / "runtime.snapshot"
    assert offline_state("init", snapshot) == 0
    initial = snapshot.read_bytes()
    with pytest.raises(FileExistsError):
        offline_state("init", snapshot)
    assert snapshot.read_bytes() == initial
    assert offline_state("migrate", snapshot) == 0
    assert snapshot.with_suffix(".previous").read_bytes() == initial
    source = tmp_path / "restore.snapshot"
    source.write_bytes(initial)
    assert offline_state("restore", snapshot, source) == 0
    assert source.read_bytes() == initial
    source.write_bytes(b"bad")
    with pytest.raises(InvalidDatabase):
        offline_state("restore", snapshot, source)
    assert snapshot.read_bytes() == initial


@pytest.mark.parametrize(
    "state,tasks", [("deployed", "1"), ("stopping", "0"), ("stopped", "1")]
)
def test_offline_commands_refuse_any_active_runtime(monkeypatch, state, tasks):
    import json

    from gg.runtime import modal_operations as operations

    monkeypatch.setattr(
        operations,
        "modal_cli",
        lambda *_: json.dumps(
            [
                {"description": "gg-runtime", "state": state, "tasks": tasks},
            ]
        ),
    )
    with pytest.raises(RuntimeError, match="stop the runtime"):
        operations.require_stopped("isolated")


def test_deploy_build_failure_keeps_previous_deployment(monkeypatch):
    from contextlib import contextmanager

    from gg.runtime import modal_operations as operations, modal_runtime

    calls = []

    @contextmanager
    def lease(*args, **kwargs):
        calls.append("lease")
        try:
            yield None
        finally:
            calls.append("release")

    def deploy(**kwargs):
        assert kwargs == {"environment_name": "isolated", "strategy": "recreate"}
        raise RuntimeError("image build failed")

    monkeypatch.setenv("GG_RUNTIME_API_KEY", "operator")
    monkeypatch.setattr(operations, "operation_lease", lease)
    monkeypatch.setattr(modal_runtime.app, "deploy", deploy)
    monkeypatch.setattr(
        operations, "modal_cli", lambda *_: pytest.fail("must not stop existing app")
    )
    monkeypatch.setattr(
        operations,
        "verify",
        lambda *_args, **_kwargs: pytest.fail("must not report success"),
    )
    with pytest.raises(RuntimeError, match="image build failed"):
        operations.main(["deploy", "--environment", "isolated"])
    assert calls == ["lease", "release"]


def test_rollover_always_recreates_and_verifies_version(monkeypatch):
    from contextlib import nullcontext

    from gg.runtime import modal_operations as operations

    calls = []
    monkeypatch.setenv("GG_RUNTIME_API_KEY", "operator")
    monkeypatch.setattr(
        operations, "operation_lease", lambda *_args, **_kwargs: nullcontext()
    )
    monkeypatch.setattr(
        operations, "verify", lambda *_args, **_kwargs: {"version": "tested"}
    )
    monkeypatch.setattr(
        operations, "modal_cli", lambda *args: calls.append(args) or "[]"
    )
    operations.main(
        ["rollover", "--environment", "isolated", "--url", "https://example.test"]
    )
    assert calls[0] == (
        "isolated",
        "app",
        "rollover",
        "gg-runtime",
        "--strategy",
        "recreate",
    )


def test_operation_lease_waits_for_actual_name_release(monkeypatch):
    from gg.runtime import modal_operations as operations

    calls = []
    owner = object()

    class Sandbox:
        def terminate(self, **kwargs):
            calls.append(kwargs)

    def create(*args, **kwargs):
        assert kwargs["app"] is owner
        assert kwargs["name"] == "state-writer"
        assert "environment_name" not in kwargs
        return Sandbox()

    monkeypatch.setattr(operations.modal.App, "lookup", lambda *_args, **_kwargs: owner)
    monkeypatch.setattr(operations.modal.Sandbox, "create", create)
    monkeypatch.setattr(operations, "runtime_image", lambda: object())
    with operations.operation_lease("isolated"):
        pass
    assert calls == [{"wait": True}]


def test_verify_confirms_observed_revision_despite_background_writes(monkeypatch):
    import httpx

    from gg.runtime import modal_operations as operations

    reports = iter(
        [
            {
                "status": "ready",
                "version": "tested",
                "revision": 5,
                "confirmed_revision": 4,
            },
            {
                "status": "ready",
                "version": "tested",
                "revision": 6,
                "confirmed_revision": 5,
            },
        ]
    )

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, path):
            body = {"status": "ok"} if path == "/health" else next(reports)
            return httpx.Response(
                200, json=body, request=httpx.Request("GET", "https://example.test")
            )

    monkeypatch.setenv("GG_RUNTIME_API_KEY", "operator")
    monkeypatch.setattr(operations.httpx, "Client", Client)
    monkeypatch.setattr(operations.time, "sleep", lambda _: None)
    report = operations.verify("https://example.test", expected_version="tested")
    assert report["confirmed_revision"] == 5
    assert report["revision"] == 6
