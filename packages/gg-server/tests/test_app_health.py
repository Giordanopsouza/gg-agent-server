from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport

from gg.server import Settings, create_app
from gg.server.__main__ import resolve_bind_host


@pytest.mark.anyio
async def test_create_app_returns_fastapi_app() -> None:
    app = create_app(Settings())
    assert app.title == "gg-agent-server"
    assert app.state.settings.host == "127.0.0.1"


@pytest.mark.anyio
async def test_health_is_liveness() -> None:
    app = create_app(Settings())
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.anyio
async def test_ready_after_lifespan_startup() -> None:
    app = create_app(Settings())
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        async with app.router.lifespan_context(app):
            response = await client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


@pytest.mark.anyio
async def test_ready_before_lifespan_is_initializing() -> None:
    app = create_app(Settings())
    assert not app.state.ready_event.is_set()
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "initializing"}


def test_resolve_bind_host_defaults_to_loopback_without_keys() -> None:
    assert resolve_bind_host(None, session_api_keys=[]) == "127.0.0.1"


def test_resolve_bind_host_defaults_to_all_interfaces_with_keys() -> None:
    assert resolve_bind_host(None, session_api_keys=["secret"]) == "0.0.0.0"


def test_resolve_bind_host_honors_explicit_host() -> None:
    assert resolve_bind_host("10.0.0.5", session_api_keys=[]) == "10.0.0.5"
