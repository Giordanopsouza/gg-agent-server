from __future__ import annotations

from dataclasses import dataclass

import httpx
import pytest
from httpx import ASGITransport

from gg.runtime import RuntimeSettings, create_app
from gg.runtime.ledger import SandboxProviderState, TaskLedger
from gg.runtime.modal_sandbox import SandboxSnapshot


_AUTH = {"X-API-Key": "control-secret"}


@dataclass
class FakeSandbox:
    url: str = "http://127.0.0.1:49152"
    healthy: bool = True
    health_checks: int = 0
    stop_calls: int = 0

    def is_healthy(self) -> bool:
        self.health_checks += 1
        return self.healthy

    def stop(self) -> None:
        self.stop_calls += 1


class FakeLauncher:
    def __init__(self) -> None:
        self.sandboxes: list[FakeSandbox] = []
        self.session_api_keys: list[str] = []

    def start(self, session_api_key: str) -> FakeSandbox:
        sandbox = FakeSandbox(url=f"http://127.0.0.1:{49151 + len(self.sandboxes) + 1}")
        self.sandboxes.append(sandbox)
        self.session_api_keys.append(session_api_key)
        return sandbox


class FailingLauncher:
    def start(self, session_api_key: str) -> FakeSandbox:
        raise RuntimeError("Docker is unavailable")


class FakeModalLifecycle:
    def __init__(self) -> None:
        self.detached: list[str] = []

    async def reconnect(self, task_id: str) -> SandboxSnapshot:
        return SandboxSnapshot(task_id, "modal-provider", SandboxProviderState.RUNNING)

    async def detach(self, task_id: str) -> SandboxSnapshot:
        self.detached.append(task_id)
        return SandboxSnapshot(task_id, "modal-provider", SandboxProviderState.RUNNING)

    async def terminate(self, task_id: str) -> SandboxSnapshot:
        raise AssertionError(f"shutdown must not terminate Modal task {task_id}")


def _app(launcher: FakeLauncher):
    return create_app(
        RuntimeSettings(
            api_key="control-secret",
            image="test-image:dev",
            task_db_path=":memory:",
        ),
        launcher=launcher,
    )


@pytest.mark.anyio
async def test_start_returns_container_url_and_distinct_session_key() -> None:
    launcher = FakeLauncher()
    app = _app(launcher)
    transport = ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://runtime"
    ) as client:
        async with app.router.lifespan_context(app):
            response = await client.post("/start", headers=_AUTH)

    assert response.status_code == 201
    payload = response.json()
    assert payload["id"]
    assert payload["url"] == "http://127.0.0.1:49152"
    assert payload["session_api_key"] == launcher.session_api_keys[0]
    assert payload["session_api_key"] != "control-secret"
    assert launcher.sandboxes[0].stop_calls == 1


@pytest.mark.anyio
async def test_get_checks_health_and_stop_marks_session_stopped() -> None:
    launcher = FakeLauncher()
    app = _app(launcher)
    transport = ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://runtime"
    ) as client:
        async with app.router.lifespan_context(app):
            started = (await client.post("/start", headers=_AUTH)).json()
            session_id = started["id"]

            running = await client.get(f"/sessions/{session_id}", headers=_AUTH)
            stopped = await client.post("/stop", headers=_AUTH, json={"id": session_id})
            after_stop = await client.get(f"/sessions/{session_id}", headers=_AUTH)

    assert running.status_code == 200
    assert running.json()["status"] == "running"
    assert launcher.sandboxes[0].health_checks == 1
    assert stopped.status_code == 200
    assert stopped.json()["status"] == "stopped"
    assert after_stop.status_code == 200
    assert after_stop.json()["status"] == "stopped"
    assert launcher.sandboxes[0].stop_calls == 1


@pytest.mark.anyio
async def test_failed_health_check_transitions_session_to_stopped() -> None:
    launcher = FakeLauncher()
    app = _app(launcher)
    transport = ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://runtime"
    ) as client:
        async with app.router.lifespan_context(app):
            started = (await client.post("/start", headers=_AUTH)).json()
            launcher.sandboxes[0].healthy = False
            response = await client.get(f"/sessions/{started['id']}", headers=_AUTH)

    assert response.status_code == 200
    assert response.json()["status"] == "stopped"
    assert launcher.sandboxes[0].stop_calls == 1


@pytest.mark.anyio
async def test_control_plane_rejects_missing_or_wrong_api_key() -> None:
    launcher = FakeLauncher()
    app = _app(launcher)
    transport = ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://runtime"
    ) as client:
        missing = await client.post("/start")
        wrong = await client.post("/start", headers={"X-API-Key": "wrong"})

    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert launcher.sandboxes == []


@pytest.mark.anyio
async def test_unknown_session_returns_404() -> None:
    app = _app(FakeLauncher())
    transport = ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://runtime"
    ) as client:
        get_response = await client.get("/sessions/missing", headers=_AUTH)
        stop_response = await client.post(
            "/stop", headers=_AUTH, json={"id": "missing"}
        )

    assert get_response.status_code == 404
    assert stop_response.status_code == 404


@pytest.mark.anyio
async def test_start_reports_launcher_failure_as_service_unavailable() -> None:
    app = create_app(
        RuntimeSettings(api_key="control-secret", task_db_path=":memory:"),
        launcher=FailingLauncher(),
    )
    transport = ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://runtime"
    ) as client:
        response = await client.post("/start", headers=_AUTH)

    assert response.status_code == 503
    assert response.json() == {"detail": "Docker is unavailable"}


@pytest.mark.anyio
async def test_shutdown_stops_legacy_docker_but_detaches_durable_modal(
    tmp_path,
) -> None:
    ledger = TaskLedger(db_path=":memory:")
    ledger.open()
    task, _ = ledger.submit(
        idempotency_key="durable-modal",
        repository="owner/repo",
        prompt="work",
        base_ref=None,
        retry_of=None,
    )
    ledger.reserve_next(capacity=1)
    ledger.begin_sandbox_creation(
        task_id=task.id,
        deployment="production",
        sandbox_name="durable-modal-sandbox",
        tags_json="{}",
        session_api_key="private",
    )
    ledger.update_sandbox_creation(
        task.id,
        provider_id="modal-provider",
        provider_state=SandboxProviderState.RUNNING,
    )
    launcher = FakeLauncher()
    modal_lifecycle = FakeModalLifecycle()
    app = create_app(
        RuntimeSettings(
            api_key="control-secret",
            task_db_path=":memory:",
            dispatch_lock_path=str(tmp_path / "dispatch.lock"),
        ),
        launcher=launcher,
        task_ledger=ledger,
        modal_lifecycle=modal_lifecycle,  # type: ignore[arg-type]
    )
    transport = ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://runtime"
    ) as client:
        async with app.router.lifespan_context(app):
            response = await client.post("/start", headers=_AUTH)
            assert response.status_code == 201

    assert launcher.sandboxes[0].stop_calls == 1
    assert modal_lifecycle.detached == [task.id]
