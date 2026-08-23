from __future__ import annotations

import asyncio
import threading
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport

from gg.sdk import ConversationStatus, EventKind, LocalConversation
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
    assert sent.json()["payload"] == {"text": "hello from http"}
    assert record.json()["status"] == ConversationStatus.IDLE
    assert [item["kind"] for item in events.json()] == [EventKind.MESSAGE]
    assert not (Path(created["working_dir"]) / "NOTES.md").exists()


@pytest.mark.anyio
async def test_post_run_finishes_and_writes_notes(tmp_path: Path) -> None:
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
    notes = Path(created["working_dir"]) / "NOTES.md"
    assert notes.is_file()
    assert "ship it" in notes.read_text(encoding="utf-8")
    kinds = [item["kind"] for item in events.json()]
    assert kinds[0] == EventKind.MESSAGE
    assert EventKind.ACTION in kinds
    assert EventKind.OBSERVATION in kinds
    seqs = [item["seq"] for item in events.json()]
    assert seqs == sorted(seqs)


@pytest.mark.anyio
async def test_run_while_already_running_returns_409(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
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
