from __future__ import annotations

import sqlite3

import httpx
import pytest
from httpx import ASGITransport

from gg.runtime import RuntimeSettings, TaskLedger, create_app


_AUTH = {"X-API-Key": "control-secret"}


def _settings(**overrides) -> RuntimeSettings:
    base = {
        "api_key": "control-secret",
        "image": "test-image:dev",
        "task_db_path": ":memory:",
        "repository_allowlist": ("owner/allowed", "org/repo"),
    }
    base.update(overrides)
    return RuntimeSettings(**base)


def _app(settings: RuntimeSettings, *, ledger: TaskLedger | None = None):
    return create_app(settings, task_ledger=ledger or TaskLedger(db_path=":memory:"))


def _payload(
    *,
    key: str,
    repo: str = "owner/allowed",
    prompt: str = "fix the bug",
    base_ref: str | None = None,
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
async def test_allowlist_rejects_unknown_repository() -> None:
    app = _app(_settings())
    transport = ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://runtime"
    ) as client:
        async with app.router.lifespan_context(app):
            response = await client.post(
                "/tasks", headers=_AUTH, json=_payload(key="k1", repo="owner/denied")
            )

    assert response.status_code == 422
    assert "not on the allowlist" in response.json()["detail"]


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


@pytest.mark.anyio
async def test_tasks_persist_across_app_restart(tmp_path) -> None:
    db_path = str(tmp_path / "tasks.sqlite")
    settings = _settings(task_db_path=db_path)

    app1 = _app(settings, ledger=TaskLedger(db_path=db_path))
    transport1 = ASGITransport(app=app1)
    async with httpx.AsyncClient(
        transport=transport1, base_url="http://runtime"
    ) as client:
        async with app1.router.lifespan_context(app1):
            await client.post("/tasks", headers=_AUTH, json=_payload(key="k1"))
            await client.post("/tasks", headers=_AUTH, json=_payload(key="k2"))

    # A second app instance over the same on-disk ledger must see prior work.
    app2 = _app(settings, ledger=TaskLedger(db_path=db_path))
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


def test_unsupported_future_schema_fails_startup(tmp_path) -> None:
    db_path = str(tmp_path / "tasks.sqlite")
    from gg.runtime.ledger import SUPPORTED_SCHEMA_VERSION

    ledger = TaskLedger(db_path=db_path)
    ledger.open()
    ledger.submit(
        idempotency_key="k1",
        repository="owner/name",
        prompt="p",
        base_ref=None,
        retry_of=None,
    )
    ledger.close()

    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE schema_meta SET value = ? WHERE key = 'schema_version'",
        (str(SUPPORTED_SCHEMA_VERSION + 1),),
    )
    conn.commit()
    conn.close()

    with pytest.raises(RuntimeError, match="unsupported task ledger schema version"):
        TaskLedger(db_path=db_path).open()
