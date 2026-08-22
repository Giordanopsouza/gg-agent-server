from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport

from gg.server import Settings, create_app


_AUTH_CHECK_PATH = "/api/_auth_check"
_SESSION_HEADER = "X-Session-API-Key"


@pytest.mark.anyio
async def test_open_mode_allows_api_without_header() -> None:
    app = create_app(Settings(session_api_keys=[]))
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.get(_AUTH_CHECK_PATH)

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.anyio
async def test_keyed_mode_rejects_missing_header() -> None:
    app = create_app(Settings(session_api_keys=["secret-one"]))
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.get(_AUTH_CHECK_PATH)

    assert response.status_code == 401


@pytest.mark.anyio
async def test_keyed_mode_rejects_wrong_header() -> None:
    app = create_app(Settings(session_api_keys=["secret-one"]))
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.get(
            _AUTH_CHECK_PATH,
            headers={_SESSION_HEADER: "wrong-key"},
        )

    assert response.status_code == 401


@pytest.mark.anyio
async def test_keyed_mode_accepts_correct_header() -> None:
    app = create_app(Settings(session_api_keys=["secret-one", "secret-two"]))
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.get(
            _AUTH_CHECK_PATH,
            headers={_SESSION_HEADER: "secret-two"},
        )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.anyio
async def test_health_stays_public_when_keys_configured() -> None:
    app = create_app(Settings(session_api_keys=["secret-one"]))
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
