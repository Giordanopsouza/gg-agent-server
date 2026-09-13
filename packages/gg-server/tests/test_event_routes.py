from __future__ import annotations

import asyncio
import threading
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport

from gg.sdk import (
    AgentProcessError,
    AgentProtocolError,
    ConversationStatus,
    EventKind,
    LocalConversation,
    local_conversation as local_conversation_module,
)
from gg.sdk.agent_backend import EventEmitter
from gg.sdk.local_workspace import LocalWorkspace
from gg.server import Settings, create_app


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        conversations_dir=tmp_path / "conversations",
        workspace_dir=tmp_path / "project",
    )


async def _start_conversation(client: httpx.AsyncClient) -> dict:
    response = await client.post(
        "/api/conversations",
        json={"working_dir": "work"},
    )
    assert response.status_code == 201
    return response.json()


class SuccessfulPiBackend:
    def run(
        self,
        prompt: str,
        workspace: LocalWorkspace,
        emit: EventEmitter,
    ) -> None:
        assert prompt == "pi prompt"
        emit(EventKind.MESSAGE, {"role": "assistant", "text": "done"})
        emit(EventKind.ACTION, {"tool": "write", "args": {}})
        emit(EventKind.OBSERVATION, {"result": "ok", "is_error": False})


class FailingPiBackend:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def run(
        self,
        prompt: str,
        workspace: LocalWorkspace,
        emit: EventEmitter,
    ) -> None:
        raise self.error


@pytest.mark.anyio
async def test_post_events_appends_message_and_does_not_run(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        async with app.router.lifespan_context(app):
            created = await _start_conversation(client)
            conversation_id = created["id"]
            sent = await client.post(
                f"/api/conversations/{conversation_id}/events",
                json={"content": "hello from http"},
            )
            record = await client.get(f"/api/conversations/{conversation_id}")
            events = await client.get(f"/api/conversations/{conversation_id}/events")

    assert sent.status_code == 200
    assert sent.json()["kind"] == EventKind.MESSAGE
    assert sent.json()["payload"] == {"role": "user", "text": "hello from http"}
    assert record.json()["status"] == ConversationStatus.IDLE
    assert [item["kind"] for item in events.json()] == [EventKind.MESSAGE]


@pytest.mark.anyio
async def test_post_run_finishes_and_lists_events(
    tmp_path: Path, scripted_agent
) -> None:
    app = create_app(_settings(tmp_path))
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        async with app.router.lifespan_context(app):
            created = await _start_conversation(client)
            conversation_id = created["id"]
            await client.post(
                f"/api/conversations/{conversation_id}/events",
                json={"content": "ship it"},
            )
            ran = await client.post(f"/api/conversations/{conversation_id}/run")
            events = await client.get(f"/api/conversations/{conversation_id}/events")

    assert ran.status_code == 200
    assert ran.json()["status"] == ConversationStatus.FINISHED
    kinds = [item["kind"] for item in events.json()]
    assert kinds[0] == EventKind.MESSAGE
    assert EventKind.ACTION in kinds
    assert EventKind.OBSERVATION in kinds
    seqs = [item["seq"] for item in events.json()]
    assert seqs == sorted(seqs)


@pytest.mark.anyio
async def test_pi_run_persists_and_lists_translated_events(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        local_conversation_module,
        "create_agent_backend",
        lambda config: SuccessfulPiBackend(),
    )
    app = create_app(_settings(tmp_path))
    transport = ASGITransport(app=app)
    published = []
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        async with app.router.lifespan_context(app):
            created = await client.post(
                "/api/conversations",
                json={"working_dir": "work", "agent": {"kind": "pi"}},
            )
            conversation_id = created.json()["id"]
            await client.post(
                f"/api/conversations/{conversation_id}/events",
                json={"content": "pi prompt"},
            )
            stream = app.state.conversation_service.event_stream(conversation_id)

            async def capture(event) -> None:
                published.append(event)

            stream.subscribe(capture)
            ran = await client.post(f"/api/conversations/{conversation_id}/run")
            listed = await client.get(
                f"/api/conversations/{conversation_id}/events"
            )

    assert ran.status_code == 200
    assert ran.json()["status"] == ConversationStatus.FINISHED
    assert [event["kind"] for event in listed.json()] == [
        EventKind.MESSAGE,
        EventKind.STATUS,
        EventKind.MESSAGE,
        EventKind.ACTION,
        EventKind.OBSERVATION,
        EventKind.STATUS,
    ]
    assert listed.json()[0]["payload"] == {"role": "user", "text": "pi prompt"}
    assert [event.kind for event in published] == [
        EventKind.STATUS,
        EventKind.MESSAGE,
        EventKind.ACTION,
        EventKind.OBSERVATION,
        EventKind.STATUS,
    ]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("error", "error_type"),
    [
        (AgentProtocolError("Pi emitted malformed JSONL"), "agent_protocol_error"),
        (AgentProcessError("Pi exited early"), "agent_process_error"),
    ],
)
async def test_pi_failure_returns_502_persists_error_and_publishes_events(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    error_type: str,
) -> None:
    monkeypatch.setattr(
        local_conversation_module,
        "create_agent_backend",
        lambda config: FailingPiBackend(error),
    )
    app = create_app(_settings(tmp_path))
    transport = ASGITransport(app=app)
    published = []
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        async with app.router.lifespan_context(app):
            created = await client.post(
                "/api/conversations",
                json={"working_dir": "work", "agent": {"kind": "pi"}},
            )
            conversation_id = created.json()["id"]
            await client.post(
                f"/api/conversations/{conversation_id}/events",
                json={"content": "pi prompt"},
            )
            stream = app.state.conversation_service.event_stream(conversation_id)

            async def capture(event) -> None:
                published.append(event)

            stream.subscribe(capture)
            ran = await client.post(f"/api/conversations/{conversation_id}/run")
            record = await client.get(f"/api/conversations/{conversation_id}")
            listed = await client.get(
                f"/api/conversations/{conversation_id}/events"
            )

    assert ran.status_code == 502
    assert record.json()["status"] == ConversationStatus.ERROR
    assert [event["kind"] for event in listed.json()][-3:] == [
        EventKind.STATUS,
        EventKind.ERROR,
        EventKind.STATUS,
    ]
    assert listed.json()[-2]["payload"]["type"] == error_type
    assert [event.kind for event in published] == [
        EventKind.STATUS,
        EventKind.ERROR,
        EventKind.STATUS,
    ]


@pytest.mark.anyio
async def test_run_while_already_running_returns_409(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scripted_agent
) -> None:
    started = threading.Event()
    release = threading.Event()
    real_run = LocalConversation.run

    def slow_run(self: LocalConversation) -> None:
        started.set()
        assert release.wait(timeout=5.0)
        real_run(self)

    monkeypatch.setattr(LocalConversation, "run", slow_run)

    app = create_app(_settings(tmp_path))
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        async with app.router.lifespan_context(app):
            created = await _start_conversation(client)
            conversation_id = created["id"]
            await client.post(
                f"/api/conversations/{conversation_id}/events",
                json={"content": "go"},
            )
            first = asyncio.create_task(
                client.post(f"/api/conversations/{conversation_id}/run")
            )
            assert await asyncio.to_thread(started.wait, 5.0)
            second = await client.post(f"/api/conversations/{conversation_id}/run")
            release.set()
            first_response = await first

    assert second.status_code == 409
    assert first_response.status_code == 200
    assert first_response.json()["status"] == ConversationStatus.FINISHED


@pytest.mark.anyio
async def test_unknown_conversation_returns_404(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        async with app.router.lifespan_context(app):
            posted = await client.post(
                "/api/conversations/missing-id/events",
                json={"content": "hello"},
            )
            listed = await client.get("/api/conversations/missing-id/events")
            ran = await client.post("/api/conversations/missing-id/run")

    assert posted.status_code == 404
    assert listed.status_code == 404
    assert ran.status_code == 404
