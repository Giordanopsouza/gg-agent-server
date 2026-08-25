from __future__ import annotations

import os

import httpx
import pytest
from httpx import ASGITransport

from gg.runtime import RuntimeSettings, create_app


@pytest.mark.docker
@pytest.mark.skipif(
    os.getenv("GG_RUN_DOCKER_TESTS") != "1",
    reason="set GG_RUN_DOCKER_TESTS=1 to run the live Docker test",
)
@pytest.mark.anyio
async def test_runtime_controls_live_agent_server_container() -> None:
    app = create_app(RuntimeSettings(api_key="live-control-secret"))
    transport = ASGITransport(app=app)
    headers = {"X-API-Key": "live-control-secret"}

    async with httpx.AsyncClient(
        transport=transport, base_url="http://runtime"
    ) as client:
        async with app.router.lifespan_context(app):
            started = await client.post("/start", headers=headers)
            assert started.status_code == 201
            session_id = started.json()["id"]

            running = await client.get(
                f"/sessions/{session_id}", headers=headers
            )
            assert running.json()["status"] == "running"

            stopped = await client.post(
                "/stop", headers=headers, json={"id": session_id}
            )
            assert stopped.json()["status"] == "stopped"
