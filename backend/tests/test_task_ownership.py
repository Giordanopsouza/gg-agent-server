"""Two browser owners and the operator against the real local task ledger."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from gg.runtime.app import create_app
from gg.runtime.config import RuntimeSettings
from gg.runtime.local_sessions import token_hash
from gg.runtime.web_auth import SESSION_COOKIE
from gg.sdk.tasks import TaskState
from test_support.sqlite_ledger import new_ledger


@pytest.fixture
def owned_app(tmp_path):
    ledger = new_ledger()
    settings = RuntimeSettings(
        api_key="operator-secret",
        web_origin="https://app.example",
        task_dispatch_enabled=False,
        dispatch_lock_path=str(tmp_path / "dispatch.lock"),
    )
    app = create_app(settings, task_ledger=ledger)
    with TestClient(app, base_url="https://app.example") as client:
        yield client, app.state.web_sessions, ledger, set()


def _as_owner(client: TestClient, provider, owner: UUID) -> None:
    token = str(uuid4())
    with provider.db.write() as tx:
        tx.connection.execute(
            "INSERT OR IGNORE INTO local_users VALUES (?, ?, ?)",
            (str(owner), str(owner), "local@example.test"),
        )
        tx.connection.execute(
            "INSERT INTO local_sessions(token_hash, owner_id, expires_at) "
            "VALUES (?, ?, ?)",
            (token_hash(token), str(owner), int(time.time()) + 3600),
        )
    client.cookies.set(SESSION_COOKIE, token)


def _submit(client: TestClient, key: str, prompt: str = "hello"):
    return client.post(
        "/tasks",
        headers={"Origin": "https://app.example"},
        json={"idempotency_key": key, "prompt": prompt},
    )


def test_http_owner_isolation_and_operator_boundary(owned_app) -> None:
    client, provider, _, task_ids = owned_app
    alice, bob = uuid4(), uuid4()
    key = f"owner-{uuid4()}"
    _as_owner(client, provider, alice)
    forged_owner = client.post(
        "/tasks",
        headers={"Origin": "https://app.example"},
        json={
            "idempotency_key": f"forged-{uuid4()}",
            "prompt": "x",
            "owner_id": str(bob),
        },
    )
    assert forged_owner.status_code == 422
    first = _submit(client, key, "Alice prompt")
    assert first.status_code == 201
    alice_task = first.json()["id"]
    task_ids.add(alice_task)
    assert first.json()["owner_id"] == str(alice)
    assert _submit(client, key, "Alice prompt").json()["id"] == alice_task
    assert _submit(client, key, "changed").status_code == 409

    _as_owner(client, provider, bob)
    second = _submit(client, key, "Bob prompt")
    assert second.status_code == 201
    bob_task = second.json()["id"]
    task_ids.add(bob_task)
    assert bob_task != alice_task
    assert [row["id"] for row in client.get("/tasks").json()] == [bob_task]
    for path in (
        f"/tasks/{alice_task}",
        f"/tasks/{alice_task}/events",
        f"/tasks/{alice_task}/result",
        f"/tasks/{alice_task}/messages/message-1",
    ):
        assert client.get(path).status_code == 404
    assert (
        client.post(
            f"/tasks/{alice_task}/messages",
            headers={"Origin": "https://app.example"},
            json={"id": "message-1", "content": "intrude"},
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/tasks/{alice_task}/cancel", headers={"Origin": "https://app.example"}
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/tasks/{alice_task}/retry",
            headers={"Origin": "https://app.example"},
            json={"idempotency_key": f"retry-{uuid4()}"},
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/tasks",
            headers={"Origin": "https://app.example"},
            json={
                "idempotency_key": f"indirect-{uuid4()}",
                "prompt": "x",
                "retry_of": alice_task,
            },
        ).status_code
        == 422
    )
    with pytest.raises(WebSocketDisconnect) as closed:
        with client.websocket_connect(
            f"/tasks/sockets/events/{alice_task}",
            headers={"Origin": "https://app.example"},
        ):
            pass
    assert closed.value.code == 1008
    assert client.get("/tasks/dispatch/status").status_code == 403
    assert client.get("/tasks", headers={"X-API-Key": "wrong"}).status_code == 401

    client.cookies.clear()
    operator = client.get("/tasks", headers={"X-API-Key": "operator-secret"})
    assert operator.status_code == 200
    assert {alice_task, bob_task} <= {row["id"] for row in operator.json()}
    legacy = client.post(
        "/tasks",
        headers={"X-API-Key": "operator-secret"},
        json={"idempotency_key": key, "prompt": "operator prompt"},
    )
    assert legacy.status_code == 201
    task_ids.add(legacy.json()["id"])
    assert legacy.json()["owner_id"] is None
    _as_owner(client, provider, alice)
    assert [row["id"] for row in client.get("/tasks").json()] == [alice_task]


def test_expired_payload_keeps_owner_scoped_deduplication(owned_app) -> None:
    client, provider, ledger, task_ids = owned_app
    alice, bob = uuid4(), uuid4()
    key = f"expired-{uuid4()}"
    _as_owner(client, provider, alice)
    task = _submit(client, key)
    assert task.status_code == 201
    task_id = task.json()["id"]
    task_ids.add(task_id)
    ledger.finish_task(task_id, state=TaskState.COMPLETED)
    ledger.expire_terminal_payloads(
        before=datetime.now(UTC) + timedelta(seconds=1),
        tombstone_retention=timedelta(days=90),
    )
    assert _submit(client, key).json()["id"] == task_id
    _as_owner(client, provider, bob)
    assert client.get(f"/tasks/{task_id}").status_code == 404
    other = _submit(client, key)
    assert other.status_code == 201
    task_ids.add(other.json()["id"])


def test_concurrent_same_key_uses_one_task_per_owner(owned_app) -> None:
    _, _, ledger, task_ids = owned_app
    alice, bob = uuid4(), uuid4()
    key = f"concurrent-{uuid4()}"

    def admit(owner: UUID, prompt: str):
        with new_ledger() as connection:
            return connection.submit(
                idempotency_key=key,
                repository=None,
                prompt=prompt,
                base_ref=None,
                retry_of=None,
                owner_id=owner,
            )

    with ThreadPoolExecutor(max_workers=8) as workers:
        submissions = list(
            workers.map(lambda owner: admit(owner, "same"), [alice] * 4 + [bob] * 4)
        )
    task_ids.update(record.id for record, _ in submissions)
    assert len(task_ids) == 2
    assert sum(created for _, created in submissions) == 2
    with new_ledger() as connection:
        assert {row.id for row in connection.list(owner_id=alice)} & task_ids == {
            submissions[0][0].id
        }
        assert {row.id for row in connection.list(owner_id=bob)} & task_ids == {
            submissions[4][0].id
        }
