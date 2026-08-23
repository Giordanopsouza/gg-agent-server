from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport

from gg.sdk import ConversationStatus
from gg.server import Settings, create_app


_SESSION_HEADER = "X-Session-API-Key"


def _settings(tmp_path: Path, *, session_api_keys: list[str] | None = None) -> Settings:
    return Settings(
        conversations_dir=tmp_path / "conversations",
        workspace_dir=tmp_path / "project",
        session_api_keys=session_api_keys or [],
    )


@pytest.mark.anyio
async def test_post_creates_conversation(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        async with app.router.lifespan_context(app):
            response = await client.post(
                "/api/conversations",
                json={"working_dir": "work"},
            )

    assert response.status_code == 201
    body = response.json()
    assert body["id"]
    assert body["status"] == ConversationStatus.IDLE
    assert body["working_dir"] == str(tmp_path / "project" / "work")


@pytest.mark.anyio
async def test_post_existing_id_reattaches(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        async with app.router.lifespan_context(app):
            created = await client.post(
                "/api/conversations",
                json={"working_dir": "work"},
            )
            conversation_id = created.json()["id"]
            response = await client.post(
                "/api/conversations",
                json={"working_dir": "other", "id": conversation_id},
            )

    assert created.status_code == 201
    assert response.status_code == 200
    assert response.json()["id"] == conversation_id
    assert response.json()["working_dir"] == created.json()["working_dir"]


@pytest.mark.anyio
async def test_get_returns_record_or_404(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        async with app.router.lifespan_context(app):
            created = await client.post(
                "/api/conversations",
                json={"working_dir": "work"},
            )
            conversation_id = created.json()["id"]
            found = await client.get(f"/api/conversations/{conversation_id}")
            missing = await client.get("/api/conversations/missing-id")

    assert found.status_code == 200
    assert found.json()["id"] == conversation_id
    assert missing.status_code == 404


@pytest.mark.anyio
async def test_list_returns_ids_from_disk(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        async with app.router.lifespan_context(app):
            first = await client.post(
                "/api/conversations",
                json={"working_dir": "alpha"},
            )
            second = await client.post(
                "/api/conversations",
                json={"working_dir": "beta"},
            )
            response = await client.get("/api/conversations")

    ids = {item["id"] for item in response.json()}
    assert response.status_code == 200
    assert ids == {first.json()["id"], second.json()["id"]}


@pytest.mark.anyio
async def test_conversation_routes_require_session_key(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, session_api_keys=["secret-one"]))
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        async with app.router.lifespan_context(app):
            denied = await client.get("/api/conversations")
            allowed = await client.get(
                "/api/conversations",
                headers={_SESSION_HEADER: "secret-one"},
            )

    assert denied.status_code == 401
    assert allowed.status_code == 200
    assert allowed.json() == []
