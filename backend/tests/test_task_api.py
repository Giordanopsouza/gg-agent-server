from __future__ import annotations

from pathlib import Path
from tempfile import gettempdir
from unittest.mock import patch
from uuid import uuid4

import httpx
import pytest
from httpx import ASGITransport
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from gg.runtime import RuntimeSettings, create_app
from gg.runtime.ledger import TaskLedger
from test_support.postgres_ledger import new_ledger


_AUTH = {"X-API-Key": "control-secret"}


def _settings(**overrides) -> RuntimeSettings:
    base = {
        "api_key": "control-secret",
        "image": "test-image:dev",
        "dispatch_lock_path": str(Path(gettempdir()) / f"gg-task-api-{uuid4()}.lock"),
    }
    base.update(overrides)
    return RuntimeSettings(**base)


def _app(settings: RuntimeSettings, *, ledger: TaskLedger | None = None):
    return create_app(settings, task_ledger=ledger or new_ledger())


def _payload(
    *,
    key: str,
    repo: str = "owner/allowed",
    prompt: str = "fix the bug",
    base_ref: str | None = "main",
    retry_of: str | None = None,
) -> dict:
    body = {
        "repository": repo,
        "prompt": prompt,
        "idempotency_key": key,
    }
    if base_ref is not None:
        body["base_ref"] = base_ref
    if retry_of is not None:
        body["retry_of"] = retry_of
    return body


@pytest.mark.anyio
async def test_submit_returns_created_with_queued_state() -> None:
    app = _app(_settings())
    transport = ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://runtime"
    ) as client:
        async with app.router.lifespan_context(app):
            response = await client.post(
                "/tasks", headers=_AUTH, json=_payload(key="k1")
            )

    assert response.status_code == 201
    body = response.json()
    assert body["state"] == "queued"
    assert body["repository"] == "owner/allowed"
    assert body["id"]
    assert body["seq"] == 1
    assert body["base_sha"] is None
    assert body["outcome_detail"] is None


@pytest.mark.anyio
async def test_dispatch_status_keeps_queued_work_visibly_pending() -> None:
    app = _app(_settings())
    transport = ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://runtime"
    ) as client:
        async with app.router.lifespan_context(app):
            await client.post("/tasks", headers=_AUTH, json=_payload(key="k1"))
            response = await client.get("/tasks/dispatch/status", headers=_AUTH)

    assert response.status_code == 200
    assert response.json()["enabled"] is False
    assert response.json()["reconciled"] is True
    assert response.json()["pending"] == 1
    assert response.json()["disabled_reason"] == "dispatch disabled"


@pytest.mark.anyio
async def test_idempotent_replay_returns_original_with_200() -> None:
    app = _app(_settings())
    transport = ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://runtime"
    ) as client:
        async with app.router.lifespan_context(app):
            first = await client.post("/tasks", headers=_AUTH, json=_payload(key="k1"))
            replay = await client.post("/tasks", headers=_AUTH, json=_payload(key="k1"))

    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.json()["id"] == first.json()["id"]


@pytest.mark.anyio
async def test_reuse_with_different_input_returns_conflict() -> None:
    app = _app(_settings())
    transport = ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://runtime"
    ) as client:
        async with app.router.lifespan_context(app):
            first = await client.post(
                "/tasks", headers=_AUTH, json=_payload(key="k1", prompt="A")
            )
            conflict = await client.post(
                "/tasks", headers=_AUTH, json=_payload(key="k1", prompt="B")
            )

    assert first.status_code == 201
    assert conflict.status_code == 409
    assert "already used" in conflict.json()["detail"]


@pytest.mark.anyio
async def test_model_catalog_validation_and_idempotency() -> None:
    app = _app(_settings())
    transport = ASGITransport(app=app)
    body = {**_payload(key="model-k1"), "model": "anthropic/claude-sonnet-4.5"}
    async with httpx.AsyncClient(
        transport=transport, base_url="http://runtime"
    ) as client:
        async with app.router.lifespan_context(app):
            catalog = await client.get("/tasks/models", headers=_AUTH)
            first = await client.post("/tasks", headers=_AUTH, json=body)
            replay = await client.post("/tasks", headers=_AUTH, json=body)
            conflict = await client.post(
                "/tasks",
                headers=_AUTH,
                json={**body, "model": "z-ai/glm-5.3-flashx"},
            )
            invalid = await client.post(
                "/tasks",
                headers=_AUTH,
                json={**_payload(key="model-k2"), "model": "unlisted/model"},
            )
            stored = await client.get(f"/tasks/{first.json()['id']}", headers=_AUTH)

    assert catalog.status_code == 200
    assert "anthropic/claude-sonnet-4.5" in catalog.json()["models"]
    assert first.status_code == 201
    assert first.json()["model"] == stored.json()["model"] == body["model"]
    assert replay.status_code == 200
    assert conflict.status_code == 409
    assert invalid.status_code == 422


@pytest.mark.anyio
async def test_repository_admits_without_allowlist_or_profile_match() -> None:
    app = _app(_settings())
    transport = ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://runtime"
    ) as client:
        async with app.router.lifespan_context(app):
            response = await client.post(
                "/tasks", headers=_AUTH, json=_payload(key="k1", repo="owner/denied")
            )

    assert response.status_code == 201
    assert response.json()["repository"] == "owner/denied"


@pytest.mark.anyio
async def test_general_task_admits_without_repository_or_github_config() -> None:
    app = _app(_settings())
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://runtime"
    ) as client:
        async with app.router.lifespan_context(app):
            response = await client.post(
                "/tasks",
                headers=_AUTH,
                json={"prompt": "summarize the task", "idempotency_key": "general-1"},
            )
    assert response.status_code == 201
    assert response.json()["repository"] is None
    assert response.json()["base_ref"] is None


@pytest.mark.anyio
async def test_repository_requires_base_ref() -> None:
    app = _app(_settings())
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://runtime"
    ) as client:
        async with app.router.lifespan_context(app):
            response = await client.post(
                "/tasks",
                headers=_AUTH,
                json=_payload(key="missing-ref", base_ref=None),
            )
    assert response.status_code == 422
    assert "base_ref is required" in response.json()["detail"]


@pytest.mark.anyio
async def test_invalid_base_ref_is_rejected() -> None:
    app = _app(_settings())
    transport = ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://runtime"
    ) as client:
        async with app.router.lifespan_context(app):
            ok = await client.post(
                "/tasks",
                headers=_AUTH,
                json=_payload(key="k1", base_ref="feature/branch"),
            )
            bad = await client.post(
                "/tasks",
                headers=_AUTH,
                json=_payload(key="k2", base_ref="bad..ref"),
            )
            spaces = await client.post(
                "/tasks",
                headers=_AUTH,
                json=_payload(key="k3", base_ref="has space"),
            )

    assert ok.status_code == 201
    assert bad.status_code == 422
    assert spaces.status_code == 422


@pytest.mark.anyio
async def test_list_returns_tasks_in_fifo_order() -> None:
    app = _app(_settings())
    transport = ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://runtime"
    ) as client:
        async with app.router.lifespan_context(app):
            await client.post("/tasks", headers=_AUTH, json=_payload(key="k1"))
            await client.post("/tasks", headers=_AUTH, json=_payload(key="k2"))
            await client.post("/tasks", headers=_AUTH, json=_payload(key="k3"))
            listed = await client.get("/tasks", headers=_AUTH)

    assert listed.status_code == 200
    assert [task["idempotency_key"] for task in listed.json()] == ["k1", "k2", "k3"]
    assert [task["seq"] for task in listed.json()] == [1, 2, 3]


@pytest.mark.anyio
async def test_get_returns_task_detail_or_404() -> None:
    app = _app(_settings())
    transport = ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://runtime"
    ) as client:
        async with app.router.lifespan_context(app):
            created = await client.post(
                "/tasks", headers=_AUTH, json=_payload(key="k1")
            )
            task_id = created.json()["id"]
            found = await client.get(f"/tasks/{task_id}", headers=_AUTH)
            missing = await client.get("/tasks/unknown", headers=_AUTH)

    assert found.status_code == 200
    assert found.json()["id"] == task_id
    assert missing.status_code == 404


@pytest.mark.anyio
async def test_tasks_require_control_plane_key() -> None:
    app = _app(_settings())
    transport = ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://runtime"
    ) as client:
        async with app.router.lifespan_context(app):
            missing = await client.post("/tasks", json=_payload(key="k1"))
            wrong = await client.post(
                "/tasks", headers={"X-API-Key": "wrong"}, json=_payload(key="k1")
            )

    assert missing.status_code == 401
    assert wrong.status_code == 401


def test_task_event_socket_requires_control_plane_key() -> None:
    app = _app(_settings())
    with TestClient(app) as client:
        created = client.post("/tasks", headers=_AUTH, json=_payload(key="k1"))
        assert created.status_code == 201
        task_id = created.json()["id"]

        with pytest.raises(WebSocketDisconnect) as missing:
            with client.websocket_connect(f"/tasks/sockets/events/{task_id}"):
                pass
        with pytest.raises(WebSocketDisconnect) as wrong:
            with client.websocket_connect(
                f"/tasks/sockets/events/{task_id}",
                headers={"X-API-Key": "wrong"},
            ):
                pass
        with client.websocket_connect(
            f"/tasks/sockets/events/{task_id}",
            headers=_AUTH,
        ):
            pass

    assert missing.value.code == 1008
    assert wrong.value.code == 1008


@pytest.mark.anyio
async def test_tasks_persist_across_app_restart(tmp_path) -> None:
    settings = _settings()

    app1 = _app(settings, ledger=new_ledger())
    transport1 = ASGITransport(app=app1)
    async with httpx.AsyncClient(
        transport=transport1, base_url="http://runtime"
    ) as client:
        async with app1.router.lifespan_context(app1):
            await client.post("/tasks", headers=_AUTH, json=_payload(key="k1"))
            await client.post("/tasks", headers=_AUTH, json=_payload(key="k2"))

    # A second app instance sees the same Postgres records.
    app2 = _app(settings, ledger=new_ledger())
    transport2 = ASGITransport(app=app2)
    async with httpx.AsyncClient(
        transport=transport2, base_url="http://runtime"
    ) as client:
        async with app2.router.lifespan_context(app2):
            listed = await client.get("/tasks", headers=_AUTH)
            new_task = await client.post(
                "/tasks", headers=_AUTH, json=_payload(key="k3")
            )

    assert [task["idempotency_key"] for task in listed.json()] == ["k1", "k2"]
    assert new_task.status_code == 201
    assert new_task.json()["seq"] == 3


def test_unsupported_future_schema_fails_startup() -> None:
    from gg.runtime.ledger import SUPPORTED_SCHEMA_VERSION

    ledger = new_ledger()
    with patch.object(
        TaskLedger, "_schema_version", return_value=SUPPORTED_SCHEMA_VERSION + 1
    ):
        with pytest.raises(
            RuntimeError, match="unsupported Postgres ledger schema version"
        ):
            ledger.open()
