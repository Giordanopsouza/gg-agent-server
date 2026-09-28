"""Two browser owners and the operator against the real local task ledger."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import psycopg
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from gg.runtime.app import create_app
from gg.runtime.config import RuntimeSettings
from gg.runtime.postgres import RuntimePostgres
from gg.runtime.postgres_ledger import PostgresTaskLedger
from gg.runtime.web_auth import SESSION_COOKIE, SupabaseAuth
from gg.sdk.tasks import TaskState


class FakeValidatedAuth(SupabaseAuth):
    async def verified_user(self, access_token: str) -> dict[str, str]:
        return {
            "id": str(UUID(access_token)),
            "email": "local@example.test",
            "session_id": str(UUID(int=3)),
        }


class ActiveSessions:
    def active(self, user_id: str, session_id: str) -> bool:
        return bool(UUID(user_id) and UUID(session_id))


@pytest.fixture
def owned_app(tmp_path):
    url = os.getenv("GG_RUNTIME_DATABASE_URL", "")
    if urlsplit(url).hostname not in {"localhost", "127.0.0.1"}:
        pytest.skip("requires local Supabase Postgres")
    database = RuntimePostgres.from_env()
    settings = RuntimeSettings(
        api_key="operator-secret",
        supabase_url="https://local.supabase.test",
        supabase_publishable_key="local-publishable",
        web_cookie_key=Fernet.generate_key().decode(),
        web_origin="https://app.example",
        task_dispatch_enabled=False,
        dispatch_lock_path=str(tmp_path / "dispatch.lock"),
    )
    provider = FakeValidatedAuth(settings)
    ledger = PostgresTaskLedger(database)
    app = create_app(
        settings,
        task_ledger=ledger,
        web_auth=provider,
        web_sessions=ActiveSessions(),
    )
    task_ids: set[str] = set()
    try:
        with TestClient(app, base_url="https://app.example") as client:
            yield client, provider, ledger, task_ids
    finally:
        with psycopg.connect(database.url, **database.connection_kwargs()) as conn:
            for table in (
                "sandbox_creations",
                "task_reservations",
                "publication_intents",
                "task_supervisions",
                "task_event_copies",
                "task_message_receipts",
                "task_results",
                "retention_tombstones",
            ):
                conn.execute(
                    f"DELETE FROM runtime_private.{table} WHERE task_id = ANY(%s)",
                    (list(task_ids),),
                )
            conn.execute(
                "DELETE FROM runtime_private.tasks WHERE id = ANY(%s)",
                (list(task_ids),),
            )


def _as_owner(client: TestClient, provider: SupabaseAuth, owner: UUID) -> None:
    client.cookies.set(
        SESSION_COOKIE,
        provider.seal({"access": str(owner), "refresh": "unused"}),
    )


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
    assert ledger._conn is not None
    row = ledger._conn.execute(
        "SELECT * FROM tasks WHERE id = ?", (task_id,)
    ).fetchone()
    ledger._expire_task_payload(
        task_id, record=row, tombstone_retention=timedelta(days=90)
    )
    assert _submit(client, key).json()["id"] == task_id
    _as_owner(client, provider, bob)
    assert client.get(f"/tasks/{task_id}").status_code == 404
    other = _submit(client, key)
    assert other.status_code == 201
    task_ids.add(other.json()["id"])


def test_concurrent_same_key_uses_one_task_per_owner(owned_app) -> None:
    _, _, ledger, task_ids = owned_app
    database = ledger._database
    alice, bob = uuid4(), uuid4()
    key = f"concurrent-{uuid4()}"

    def admit(owner: UUID, prompt: str):
        with PostgresTaskLedger(database) as connection:
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
    with PostgresTaskLedger(database) as connection:
        assert {row.id for row in connection.list(owner_id=alice)} & task_ids == {
            submissions[0][0].id
        }
        assert {row.id for row in connection.list(owner_id=bob)} & task_ids == {
            submissions[4][0].id
        }
