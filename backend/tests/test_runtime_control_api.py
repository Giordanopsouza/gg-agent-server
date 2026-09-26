from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport

from gg.runtime import RuntimeSettings, create_app
from gg.runtime.ledger import SandboxProviderState, TaskLedger
from gg.runtime.modal_sandbox import SandboxSnapshot


_AUTH = {"X-API-Key": "control-secret"}
_TASK = {"prompt": "hello", "idempotency_key": "k1"}


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


@pytest.mark.anyio
async def test_control_plane_rejects_missing_or_wrong_api_key() -> None:
    app = create_app(RuntimeSettings(api_key="control-secret", task_db_path=":memory:"))
    transport = ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://runtime"
    ) as client:
        missing = await client.post("/tasks", json=_TASK)
        wrong = await client.post("/tasks", headers={"X-API-Key": "wrong"}, json=_TASK)

    assert missing.status_code == 401
    assert wrong.status_code == 401


@pytest.mark.anyio
async def test_configured_web_origin_can_preflight_api_key() -> None:
    app = create_app(
        RuntimeSettings(
            api_key="control-secret",
            task_db_path=":memory:",
            cors_origins=("http://localhost:5173",),
        )
    )
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://runtime"
    ) as client:
        allowed = await client.options(
            "/tasks",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "x-api-key,content-type",
            },
        )
        denied = await client.options(
            "/tasks",
            headers={
                "Origin": "https://untrusted.example",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "x-api-key",
            },
        )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert denied.status_code == 400


@pytest.mark.anyio
async def test_shutdown_detaches_durable_modal(tmp_path) -> None:
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
    modal_lifecycle = FakeModalLifecycle()
    app = create_app(
        RuntimeSettings(
            api_key="control-secret",
            task_db_path=":memory:",
            dispatch_lock_path=str(tmp_path / "dispatch.lock"),
        ),
        task_ledger=ledger,
        modal_lifecycle=modal_lifecycle,  # type: ignore[arg-type]
    )
    transport = ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://runtime"
    ) as client:
        async with app.router.lifespan_context(app):
            response = await client.get("/health")
            assert response.status_code == 200

    assert modal_lifecycle.detached == [task.id]
