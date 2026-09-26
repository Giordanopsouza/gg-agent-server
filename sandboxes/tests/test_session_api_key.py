from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport

from gg.server import Settings, create_app


_CONVERSATIONS_PATH = "/api/conversations"
_SESSION_HEADER = "X-Session-API-Key"


def _settings(tmp_path: Path, *, keys: list[str]) -> Settings:
    return Settings(
        conversations_dir=tmp_path / "conversations",
        workspace_dir=tmp_path / "project",
        session_api_keys=keys,
    )


@pytest.mark.anyio
async def test_open_mode_allows_api_without_header(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, keys=[]))
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        async with app.router.lifespan_context(app):
            response = await client.get(_CONVERSATIONS_PATH)

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.anyio
async def test_keyed_mode_rejects_missing_header(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, keys=["secret-one"]))
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.get(_CONVERSATIONS_PATH)

    assert response.status_code == 401


@pytest.mark.anyio
async def test_keyed_mode_rejects_wrong_header(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, keys=["secret-one"]))
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.get(
            _CONVERSATIONS_PATH,
            headers={_SESSION_HEADER: "wrong-key"},
        )

    assert response.status_code == 401


@pytest.mark.anyio
async def test_keyed_mode_accepts_correct_header(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, keys=["secret-one", "secret-two"]))
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        async with app.router.lifespan_context(app):
            response = await client.get(
                _CONVERSATIONS_PATH,
                headers={_SESSION_HEADER: "secret-two"},
            )

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.anyio
async def test_health_stays_public_when_keys_configured(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, keys=["secret-one"]))
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
