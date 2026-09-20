from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from gg.runtime.config import RuntimeSettings
from gg.runtime.ledger import SandboxProviderState, TaskLedger
from gg.runtime.modal_sandbox import (
    AmbiguousProviderStateError,
    ConflictingSandboxesError,
    ModalLifecycleError,
    ModalProvider,
    ModalSandboxLifecycle,
    SandboxConnection,
    lifecycle_from_settings,
)


@dataclass
class FakeHandle:
    object_id: str
    tags: dict[str, str]
    return_code: int | None = None


class FakeProvider:
    def __init__(self, ledger: TaskLedger) -> None:
        self.ledger = ledger
        self.handles: dict[str, FakeHandle] = {}
        self.create_calls: list[dict[str, object]] = []
        self.detached: list[str] = []
        self.raise_after_create = False
        self.fail_connect = False
        self.fail_poll = False
        self.fail_terminate = False
        self.provider_id_seen_before_ready: str | None = None

    async def create(self, **kwargs: object) -> FakeHandle:
        record = self.ledger.get_sandbox_creation("task-1")
        assert record is not None, "intent must be durable before provider create"
        self.create_calls.append(kwargs)
        handle = FakeHandle("sb-1", kwargs["tags"])  # type: ignore[arg-type]
        self.handles[handle.object_id] = handle
        if self.raise_after_create:
            raise ConnectionError("response lost")
        return handle

    async def from_id(self, provider_id: str) -> FakeHandle:
        return self.handles[provider_id]

    async def find(self, *, tags: dict[str, str]) -> list[FakeHandle]:
        return [handle for handle in self.handles.values() if handle.tags == tags]

    async def poll(self, handle: FakeHandle) -> int | None:
        if self.fail_poll:
            raise ConnectionError("provider unreachable")
        return handle.return_code

    async def wait_until_ready(self, handle: FakeHandle, *, timeout: int) -> None:
        del timeout
        record = self.ledger.get_sandbox_creation("task-1")
        assert record is not None
        self.provider_id_seen_before_ready = record.provider_id

    async def connect_token(self, handle: FakeHandle, *, port: int) -> tuple[str, str]:
        del handle, port
        if self.fail_connect:
            raise ConnectionError("health/connect unavailable")
        return "https://sandbox.example", "modal-connect-secret"

    async def terminate(self, handle: FakeHandle) -> None:
        if self.fail_terminate:
            raise ConnectionError("response lost")
        handle.return_code = 137

    async def detach(self, handle: FakeHandle) -> None:
        self.detached.append(handle.object_id)


def _ledger() -> TaskLedger:
    ledger = TaskLedger(db_path=":memory:")
    ledger.open()
    record, _ = ledger.submit(
        idempotency_key="submission-1",
        repository="owner/repo",
        prompt="do work",
        base_ref=None,
        retry_of=None,
    )
    # Stable id keeps fake-provider assertions clear while preserving the FK.
    assert ledger._conn is not None  # noqa: SLF001
    ledger._conn.execute(  # noqa: SLF001
        "UPDATE tasks SET id = 'task-1' WHERE id = ?", (record.id,)
    )
    return ledger


@pytest.mark.anyio
async def test_create_persists_intent_identity_and_provider_id_before_ready() -> None:
    ledger = _ledger()
    provider = FakeProvider(ledger)
    lifecycle = ModalSandboxLifecycle(
        ledger=ledger, provider=provider, deployment="prod/east"
    )

    snapshot = await lifecycle.create("task-1")

    assert snapshot.state is SandboxProviderState.RUNNING
    assert snapshot.provider_id == "sb-1"
    assert provider.provider_id_seen_before_ready == "sb-1"
    call = provider.create_calls[0]
    assert call["cpu"] == (2.0, 2.0)
    assert call["memory"] == (4096, 4096)
    assert call["startup_timeout"] == 300
    assert call["provider_timeout"] == 4200
    assert call["name"].startswith("gg-prod-east-")  # type: ignore[union-attr]
    assert call["tags"] == {
        "gg_identity": "prod/east:task-1",
        "gg_deployment": "prod/east",
        "gg_task_id": "task-1",
    }
    ledger.close()


@pytest.mark.anyio
async def test_lost_create_response_is_discovered_without_second_create() -> None:
    ledger = _ledger()
    provider = FakeProvider(ledger)
    provider.raise_after_create = True
    first = ModalSandboxLifecycle(
        ledger=ledger, provider=provider, deployment="production"
    )

    with pytest.raises(AmbiguousProviderStateError, match="create response"):
        await first.create("task-1")

    provider.raise_after_create = False
    fresh_client = ModalSandboxLifecycle(
        ledger=ledger, provider=provider, deployment="production"
    )
    snapshot = await fresh_client.create("task-1")

    assert snapshot.state is SandboxProviderState.RUNNING
    assert snapshot.provider_id == "sb-1"
    assert len(provider.create_calls) == 1
    ledger.close()


@pytest.mark.anyio
async def test_provider_status_failure_is_unknown_not_stopped() -> None:
    ledger = _ledger()
    provider = FakeProvider(ledger)
    lifecycle = ModalSandboxLifecycle(
        ledger=ledger, provider=provider, deployment="production"
    )
    await lifecycle.create("task-1")
    provider.fail_poll = True

    snapshot = await lifecycle.inspect("task-1")

    assert snapshot.state is SandboxProviderState.UNKNOWN
    assert "status failed" in (snapshot.detail or "")
    ledger.close()


@pytest.mark.anyio
async def test_failed_authenticated_connection_does_not_claim_termination() -> None:
    ledger = _ledger()
    provider = FakeProvider(ledger)
    lifecycle = ModalSandboxLifecycle(
        ledger=ledger, provider=provider, deployment="production"
    )
    await lifecycle.create("task-1")
    provider.fail_connect = True

    with pytest.raises(AmbiguousProviderStateError, match="unreachable"):
        await lifecycle.connect("task-1")

    record = ledger.get_sandbox_creation("task-1")
    assert record is not None
    assert record.provider_state is SandboxProviderState.UNKNOWN
    ledger.close()


@pytest.mark.anyio
async def test_connection_is_https_authenticated_and_secrets_are_redacted() -> None:
    ledger = _ledger()
    provider = FakeProvider(ledger)
    lifecycle = ModalSandboxLifecycle(
        ledger=ledger, provider=provider, deployment="production"
    )
    await lifecycle.create("task-1")

    connection = await lifecycle.connect("task-1")
    websocket_url, headers = connection.websocket_target("/sockets/events/id")

    assert websocket_url == "wss://sandbox.example/sockets/events/id"
    assert headers["Authorization"] == "Bearer modal-connect-secret"
    assert headers["X-API-Key"]
    assert connection.websocket_auth_frame() == {
        "type": "auth",
        "session_api_key": headers["X-API-Key"],
    }
    rendered = repr(connection)
    assert "modal-connect-secret" not in rendered
    assert headers["X-API-Key"] not in rendered
    with pytest.raises(ModalLifecycleError, match="encrypted HTTPS"):
        SandboxConnection("http://unsafe.example", "token", "key")
    ledger.close()


@pytest.mark.anyio
async def test_failed_health_request_is_unknown_not_stopped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = _ledger()
    provider = FakeProvider(ledger)
    lifecycle = ModalSandboxLifecycle(
        ledger=ledger, provider=provider, deployment="production"
    )
    await lifecycle.create("task-1")

    def failed_client(self: SandboxConnection, **kwargs: object):
        del self, kwargs

        async def fail(_: object) -> None:
            raise httpx.ConnectError("unreachable")

        return httpx.AsyncClient(
            transport=httpx.MockTransport(fail), base_url="https://sandbox.example"
        )

    import httpx

    monkeypatch.setattr(SandboxConnection, "http_client", failed_client)
    snapshot = await lifecycle.health("task-1")

    assert snapshot.state is SandboxProviderState.UNKNOWN
    assert "health request failed" in (snapshot.detail or "")
    ledger.close()


@pytest.mark.anyio
async def test_termination_response_loss_remains_unknown() -> None:
    ledger = _ledger()
    provider = FakeProvider(ledger)
    lifecycle = ModalSandboxLifecycle(
        ledger=ledger, provider=provider, deployment="production"
    )
    await lifecycle.create("task-1")
    provider.fail_terminate = True

    with pytest.raises(AmbiguousProviderStateError, match="termination"):
        await lifecycle.terminate("task-1")

    record = ledger.get_sandbox_creation("task-1")
    assert record is not None
    assert record.provider_state is SandboxProviderState.UNKNOWN
    ledger.close()


@pytest.mark.anyio
async def test_terminate_confirms_stopped_and_detach_leaves_running() -> None:
    ledger = _ledger()
    provider = FakeProvider(ledger)
    lifecycle = ModalSandboxLifecycle(
        ledger=ledger, provider=provider, deployment="production"
    )
    await lifecycle.create("task-1")

    detached = await lifecycle.detach("task-1")
    stopped = await lifecycle.terminate("task-1")

    assert detached.state is SandboxProviderState.RUNNING
    assert provider.detached == ["sb-1"]
    assert stopped.state is SandboxProviderState.STOPPED
    assert stopped.detail == "provider exit code 137"
    ledger.close()


@pytest.mark.anyio
async def test_conflicting_discovery_blocks_adoption() -> None:
    ledger = _ledger()
    provider = FakeProvider(ledger)
    lifecycle = ModalSandboxLifecycle(
        ledger=ledger, provider=provider, deployment="production"
    )
    tags = {
        "gg_identity": "production:task-1",
        "gg_deployment": "production",
        "gg_task_id": "task-1",
    }
    ledger.begin_sandbox_creation(
        task_id="task-1",
        deployment="production",
        sandbox_name="gg-production-fixed",
        tags_json=json.dumps(tags, sort_keys=True, separators=(",", ":")),
        session_api_key="private-key",
    )
    provider.handles = {
        "sb-1": FakeHandle("sb-1", tags),
        "sb-2": FakeHandle("sb-2", tags),
    }

    with pytest.raises(ConflictingSandboxesError):
        await lifecycle.reconnect("task-1")

    record = ledger.get_sandbox_creation("task-1")
    assert record is not None
    assert record.provider_state is SandboxProviderState.UNKNOWN
    ledger.close()


def test_sandbox_credentials_are_private_to_creation_record() -> None:
    ledger = _ledger()
    _, created = ledger.begin_sandbox_creation(
        task_id="task-1",
        deployment="production",
        sandbox_name="gg-production-fixed",
        tags_json="{}",
        session_api_key="sandbox-secret",
    )

    public_task = ledger.get("task-1")

    assert created is True
    assert public_task is not None
    assert "sandbox-secret" not in public_task.model_dump_json()
    ledger.close()


@pytest.mark.anyio
async def test_settings_factory_wires_configured_resource_tuples_and_timeouts() -> None:
    ledger = _ledger()
    provider = FakeProvider(ledger)
    settings = RuntimeSettings(
        api_key="control-secret",
        modal_deployment="configured",
        modal_cpu_request=1.5,
        modal_cpu_limit=2.5,
        modal_memory_request_mib=2048,
        modal_memory_limit_mib=6144,
        modal_startup_timeout_seconds=45,
        modal_provider_timeout_seconds=600,
    )
    lifecycle = lifecycle_from_settings(
        ledger=ledger, settings=settings, provider=provider
    )

    await lifecycle.create("task-1")

    call = provider.create_calls[0]
    assert call["cpu"] == (1.5, 2.5)
    assert call["memory"] == (2048, 6144)
    assert call["startup_timeout"] == 45
    assert call["provider_timeout"] == 600
    ledger.close()


@pytest.mark.anyio
async def test_concrete_modal_provider_uses_standard_sandbox_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    app = type("App", (), {"app_id": "ap-1"})()
    image = object()
    handle = FakeHandle("sb-concrete", {})

    monkeypatch.setattr(
        "gg.runtime.modal_sandbox.modal.App.lookup", lambda *args, **kwargs: app
    )
    monkeypatch.setattr(
        "gg.runtime.modal_sandbox.modal.Image.from_name",
        lambda *args, **kwargs: image,
    )

    def create(*args: str, **kwargs: object) -> FakeHandle:
        captured["args"] = args
        captured.update(kwargs)
        return handle

    monkeypatch.setattr("gg.runtime.modal_sandbox.modal.Sandbox.create", create)
    monkeypatch.setattr(
        "gg.runtime.modal_sandbox.modal.Probe.with_tcp", lambda port: ("tcp", port)
    )
    provider = ModalProvider(
        app_name="deployed-app", image_name="gg-agent-server:versioned"
    )

    result = await provider.create(
        name="gg-production-task",
        tags={"gg_task_id": "task-1"},
        session_api_key="session-secret",
        cpu=(2.0, 2.0),
        memory=(4096, 4096),
        startup_timeout=300,
        provider_timeout=4200,
    )

    assert result is handle
    assert captured["args"] == (
        "python",
        "-m",
        "gg.server",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
    )
    assert captured["app"] is app
    assert captured["image"] is image
    assert captured["name"] == "gg-production-task"
    assert captured["tags"] == {"gg_task_id": "task-1"}
    assert captured["env"] == {"GG_SESSION_API_KEYS": "session-secret"}
    assert captured["cpu"] == (2.0, 2.0)
    assert captured["memory"] == (4096, 4096)
    assert captured["timeout"] == 4200
    assert captured["readiness_probe"] == ("tcp", 8000)
    assert "unencrypted_ports" not in captured
