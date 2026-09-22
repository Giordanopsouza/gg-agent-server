"""Integration tests for control-plane task supervision."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport

from gg.runtime import RuntimeSettings, create_app
from gg.runtime.ledger import SandboxProviderState, TaskLedger
from gg.runtime.modal_sandbox import SandboxConnection, SandboxSnapshot
from gg.runtime.task_supervision.manager import TaskSupervisionManager
from gg.sdk.domain import Event, EventKind, MessageDeliveryStatus, MessageReceipt
from gg.sdk.task_execution import (
    AgentOutcome,
    CheckOutcome,
    StartTaskExecutionRequest,
    TaskExecutionPhase,
    TaskExecutionRecord,
    TaskResultManifest,
)
from gg.sdk.tasks import TaskState


_AUTH = {"X-API-Key": "control-secret"}


@dataclass
class FakeAgentState:
    executions: dict[str, TaskExecutionRecord] = field(default_factory=dict)
    manifests: dict[str, TaskResultManifest] = field(default_factory=dict)
    events: dict[str, list[Event]] = field(default_factory=dict)
    receipts: dict[tuple[str, str], MessageReceipt] = field(default_factory=dict)
    phase: TaskExecutionPhase = TaskExecutionPhase.COMPLETED
    conversation_on_start: bool = True
    distinct_execution_id: bool = False


def _build_fake_agent(state: FakeAgentState) -> FastAPI:
    app = FastAPI()

    @app.post("/api/task-executions/start")
    async def start(body: StartTaskExecutionRequest) -> TaskExecutionRecord:
        existing = next(
            (
                item
                for item in state.executions.values()
                if item.start_key == body.start_key
            ),
            None,
        )
        if existing is not None:
            return existing
        conversation_id = (
            f"conv-{body.task_id}" if state.conversation_on_start else None
        )
        record = TaskExecutionRecord(
            execution_id=(
                f"exec-{body.task_id}" if state.distinct_execution_id else body.task_id
            ),
            task_id=body.task_id,
            repository=body.repository,
            start_key=body.start_key,
            phase=(
                TaskExecutionPhase.PREPARING
                if not state.conversation_on_start
                else state.phase
            ),
            task_branch=body.task_branch,
            base_ref=body.base_ref,
            deadline_at=body.deadline_at,
            conversation_id=conversation_id,
        )
        state.executions[record.execution_id] = record
        if conversation_id is not None:
            state.events[conversation_id] = [
                Event(seq=1, kind=EventKind.STATUS, payload={"status": "running"})
            ]
        manifest = TaskResultManifest(
            task_id=body.task_id,
            execution_id=record.execution_id,
            repository=body.repository,
            task_branch=body.task_branch,
            base_ref=body.base_ref,
            base_sha="abc123" if body.repository else None,
            agent_outcome=(
                AgentOutcome.NO_CHANGES if body.repository else AgentOutcome.SUCCEEDED
            ),
            check_outcome=CheckOutcome.NOT_RUN,
            conversation_id=conversation_id or f"conv-{body.task_id}",
            completed_at=datetime.now(UTC),
        )
        state.manifests[record.execution_id] = manifest
        return record

    @app.get("/api/task-executions/{execution_id}")
    async def get_execution(execution_id: str) -> TaskExecutionRecord:
        record = state.executions[execution_id]
        if record.conversation_id is None:
            conversation_id = f"conv-{record.task_id}"
            record = record.model_copy(
                update={
                    "conversation_id": conversation_id,
                    "phase": state.phase,
                }
            )
            state.executions[execution_id] = record
            state.events.setdefault(
                conversation_id,
                [Event(seq=1, kind=EventKind.STATUS, payload={"status": "running"})],
            )
        return record

    @app.get("/api/task-executions/{execution_id}/manifest")
    async def get_manifest(execution_id: str) -> TaskResultManifest:
        return state.manifests[execution_id]

    @app.get("/api/conversations/{conversation_id}/events")
    async def list_events(conversation_id: str) -> list[Event]:
        return state.events.get(conversation_id, [])

    @app.post("/api/conversations/{conversation_id}/messages")
    async def steer(conversation_id: str, body: dict[str, str]) -> MessageReceipt:
        receipt = MessageReceipt(
            id=body["id"],
            content=body["content"],
            status=MessageDeliveryStatus.DELIVERED,
        )
        state.receipts[(conversation_id, body["id"])] = receipt
        return receipt

    @app.get("/api/conversations/{conversation_id}/messages/{message_id}")
    async def get_receipt(conversation_id: str, message_id: str) -> MessageReceipt:
        return state.receipts[(conversation_id, message_id)]

    return app


class FakeSandboxHttpConnection:
    def __init__(self, *, app: FastAPI) -> None:
        self._inner = SandboxConnection(
            base_url="https://sandbox.test",
            _connect_token="token",
            _session_api_key="session-key",
        )
        self._transport = ASGITransport(app=app)

    def http_client(self, **kwargs: Any) -> httpx.AsyncClient:
        headers = dict(kwargs.pop("headers", {}))
        headers.update(self._inner._headers())
        return httpx.AsyncClient(
            base_url="https://sandbox.test",
            transport=self._transport,
            headers=headers,
            **kwargs,
        )


@dataclass
class ConnectableFakeLifecycle:
    ledger: TaskLedger
    agent_app: FastAPI
    terminate_calls: list[str] = field(default_factory=list)

    async def create(self, task_id: str) -> SandboxSnapshot:
        if self.ledger.get_sandbox_creation(task_id) is None:
            self.ledger.begin_sandbox_creation(
                task_id=task_id,
                deployment="production",
                sandbox_name=f"sandbox-{task_id}",
                tags_json="{}",
                session_api_key="session-key",
            )
            self.ledger.update_sandbox_creation(
                task_id,
                provider_id="provider",
                provider_state=SandboxProviderState.RUNNING,
            )
        return SandboxSnapshot(task_id, "provider", SandboxProviderState.RUNNING)

    async def reconnect(self, task_id: str) -> SandboxSnapshot:
        creation = self.ledger.get_sandbox_creation(task_id)
        state = (
            creation.provider_state
            if creation is not None
            else SandboxProviderState.RUNNING
        )
        provider_id = creation.provider_id if creation else "provider"
        return SandboxSnapshot(task_id, provider_id, state)

    async def connect(self, task_id: str) -> FakeSandboxHttpConnection:
        return FakeSandboxHttpConnection(app=self.agent_app)

    async def detach(self, task_id: str) -> SandboxSnapshot:
        return await self.reconnect(task_id)

    async def terminate(self, task_id: str) -> SandboxSnapshot:
        self.terminate_calls.append(task_id)
        self.ledger.update_sandbox_creation(
            task_id,
            provider_state=SandboxProviderState.STOPPED,
            detail="terminated",
        )
        return SandboxSnapshot(task_id, "provider", SandboxProviderState.STOPPED)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_supervision_archives_events_and_completes_no_changes_task(
    tmp_path,
) -> None:
    state = FakeAgentState()
    agent_app = _build_fake_agent(state)
    ledger = TaskLedger(db_path=str(tmp_path / "tasks.sqlite"))
    ledger.open()
    lifecycle = ConnectableFakeLifecycle(ledger=ledger, agent_app=agent_app)
    settings = RuntimeSettings(
        api_key="control-secret",
        task_db_path=str(tmp_path / "tasks.sqlite"),
        task_dispatch_enabled=True,
        dispatch_lock_path=str(tmp_path / "dispatch.lock"),
    )
    supervision = TaskSupervisionManager(
        ledger=ledger,
        lifecycle=lifecycle,  # type: ignore[arg-type]
        settings=settings,
        publisher=None,
    )
    app = create_app(
        settings,
        task_ledger=ledger,
        modal_lifecycle=lifecycle,  # type: ignore[arg-type]
        task_supervision=supervision,
    )
    transport = ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://runtime"
    ) as client:
        async with app.router.lifespan_context(app):
            created = await client.post(
                "/tasks",
                headers=_AUTH,
                json={
                    "prompt": "do work",
                    "idempotency_key": "k1",
                },
            )
            task_id = created.json()["id"]
            for _ in range(50):
                await app.state.task_scheduler.dispatch_once()
                record = ledger.get(task_id)
                assert record is not None
                if record.state is TaskState.COMPLETED:
                    break
                await asyncio.sleep(0.05)
            events = await client.get(f"/tasks/{task_id}/events", headers=_AUTH)
            result = await client.get(f"/tasks/{task_id}/result", headers=_AUTH)

    assert created.status_code == 201
    assert events.status_code == 200
    assert len(events.json()) == 1
    assert result.json()["state"] == "completed"
    assert result.json()["manifest"]["repository"] is None
    assert result.json()["publication"] is None
    assert result.json()["evidence_complete"] is True
    assert lifecycle.terminate_calls == [task_id]


@pytest.mark.anyio
async def test_supervision_copies_events_when_conversation_appears_after_start(
    tmp_path,
) -> None:
    state = FakeAgentState(conversation_on_start=False, distinct_execution_id=True)
    agent_app = _build_fake_agent(state)
    ledger = TaskLedger(db_path=str(tmp_path / "tasks.sqlite"))
    ledger.open()
    lifecycle = ConnectableFakeLifecycle(ledger=ledger, agent_app=agent_app)
    settings = RuntimeSettings(
        api_key="control-secret",
        task_db_path=str(tmp_path / "tasks.sqlite"),
        task_dispatch_enabled=True,
        dispatch_lock_path=str(tmp_path / "dispatch.lock"),
    )
    supervision = TaskSupervisionManager(
        ledger=ledger,
        lifecycle=lifecycle,  # type: ignore[arg-type]
        settings=settings,
        publisher=None,
    )
    app = create_app(
        settings,
        task_ledger=ledger,
        modal_lifecycle=lifecycle,  # type: ignore[arg-type]
        task_supervision=supervision,
    )
    transport = ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://runtime"
    ) as client:
        async with app.router.lifespan_context(app):
            created = await client.post(
                "/tasks",
                headers=_AUTH,
                json={
                    "repository": "owner/repo",
                    "base_ref": "main",
                    "prompt": "do work",
                    "idempotency_key": "k-deferred-events",
                },
            )
            task_id = created.json()["id"]
            live = supervision.subscribe_events(task_id)
            for _ in range(50):
                await app.state.task_scheduler.dispatch_once()
                record = ledger.get(task_id)
                assert record is not None
                if record.state is TaskState.COMPLETED:
                    break
                await asyncio.sleep(0.05)
            events = await client.get(f"/tasks/{task_id}/events", headers=_AUTH)
            result = await client.get(f"/tasks/{task_id}/result", headers=_AUTH)

    assert created.status_code == 201
    assert events.status_code == 200
    assert len(events.json()) == 1
    assert events.json()[0]["event"]["payload"] == {"status": "running"}
    copied = live.get_nowait()
    assert copied.event.payload == {"status": "running"}
    assert live.empty()
    assert result.json()["state"] == "completed"


@pytest.mark.anyio
async def test_cancel_queued_task_is_idempotent(tmp_path) -> None:
    ledger = TaskLedger(db_path=":memory:")
    ledger.open()
    settings = RuntimeSettings(
        api_key="control-secret",
        task_db_path=":memory:",
        dispatch_lock_path=str(tmp_path / "dispatch.lock"),
    )
    app = create_app(settings, task_ledger=ledger)
    transport = ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://runtime"
    ) as client:
        async with app.router.lifespan_context(app):
            task_id = (
                await client.post(
                    "/tasks",
                    headers=_AUTH,
                    json={
                        "prompt": "do work",
                        "idempotency_key": "k-cancel",
                    },
                )
            ).json()["id"]
            first = await client.post(f"/tasks/{task_id}/cancel", headers=_AUTH)
            second = await client.post(f"/tasks/{task_id}/cancel", headers=_AUTH)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["state"] == "cancelled"
    assert second.json()["state"] == "cancelled"
