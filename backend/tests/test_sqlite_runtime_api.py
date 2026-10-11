"""Integrated Google/SQLite HTTP and WebSocket with controlled providers."""

import asyncio
import hashlib
import hmac
import sqlite3
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from test_google_auth import callback, google_app as google_app, start

from gg.runtime.app import create_app
from gg.runtime.github_connection import GitHubClient
from gg.runtime.ledger import TaskLedger
from gg.runtime.web_auth import SESSION_COOKIE


@pytest.fixture
def runtime(google_app, tmp_path):
    _, settings, state, provider, sessions, checkpoints = google_app
    settings = settings.model_copy(
        update={
            "web_cookie_key": Fernet.generate_key().decode(),
            "openrouter_vault_key": Fernet.generate_key().decode(),
            "github_connection_key": Fernet.generate_key().decode(),
            "github_app_client_id": "Iv1.client",
            "github_app_client_secret": "client-secret",
            "github_webhook_secret": "webhook-secret",
            "dispatch_lock_path": str(tmp_path / "dispatch.lock"),
        }
    )
    provider.settings = settings
    github_state = {"id": 42, "exchanges": 0}

    def respond(request):
        if request.url.path == "/login/oauth/access_token":
            github_state["exchanges"] += 1
            return httpx.Response(200, json={"access_token": "github-secret"})
        if request.url.path == "/user":
            return httpx.Response(
                200, json={"id": github_state["id"], "login": "alice"}
            )
        if request.url.path == "/user/installations":
            return httpx.Response(
                200,
                json={
                    "installations": [
                        {"id": 99, "account": {"login": "org", "type": "Organization"}}
                    ]
                },
            )
        raise AssertionError(request.url)

    ledger = TaskLedger(sessions.db, checkpoints)
    app = create_app(
        settings,
        task_ledger=ledger,
        web_auth=provider,
        web_sessions=sessions,
        github_client=GitHubClient(settings, httpx.MockTransport(respond)),
        checkpoints=checkpoints,
    )
    with TestClient(app, base_url=settings.web_origin) as client:
        yield client, state, sessions, checkpoints, ledger, github_state
    # google_app owns the DB and closes it after all runtime services stop.


def login(client, state, sub):
    state["claims"] = {"sub": sub, "email": sub + "@example.com"}
    query, _ = start(client, state)
    assert callback(client, query).status_code == 303
    return client.cookies.get(SESSION_COOKIE)


def test_authenticated_admission_ownership_websocket_and_logout(runtime):
    client, state, sessions, checkpoints, ledger, _ = runtime
    a = login(client, state, "a")
    response = client.post(
        "/tasks",
        headers={"Origin": "https://app.example"},
        json={"prompt": "write hello", "idempotency_key": "same"},
    )
    assert response.status_code == 201
    task = response.json()
    with sqlite3.connect(checkpoints.snapshot) as durable_db:
        assert durable_db.execute(
            "SELECT id FROM tasks WHERE id=?", (task["id"],)
        ).fetchone()
    assert (
        client.post(
            "/tasks",
            headers={"Origin": "https://app.example"},
            json={"prompt": "write hello", "idempotency_key": "same"},
        ).status_code
        == 200
    )
    assert client.get("/tasks/" + task["id"]).status_code == 200
    with client.websocket_connect(
        "wss://app.example/tasks/sockets/events/" + task["id"],
        headers={"Origin": "https://app.example"},
    ):
        pass
    b = login(client, state, "b")
    assert a != b
    assert client.get("/tasks").json() == []
    assert client.get("/tasks/" + task["id"]).status_code == 404
    for suffix in ("events", "result", "messages/forged"):
        assert client.get("/tasks/" + task["id"] + "/" + suffix).status_code == 404
    assert (
        client.post(
            "/tasks/" + task["id"] + "/messages",
            headers={"Origin": "https://app.example"},
            json={"id": "forged", "content": "foreign"},
        ).status_code
        == 404
    )
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            "wss://app.example/tasks/sockets/events/" + task["id"],
            headers={"Origin": "https://app.example"},
        ):
            pass
    assert client.get("/ready").status_code == 401
    assert client.get("/tasks/dispatch/status").status_code == 403
    assert (
        client.post(
            "/auth/logout", headers={"Origin": "https://app.example"}
        ).status_code
        == 200
    )
    client.cookies.set(SESSION_COOKIE, b)
    assert client.get("/tasks").status_code == 401


def test_git_callback_binding_replay_webhook_and_credentials(runtime):
    client, state, sessions, checkpoints, ledger, github = runtime
    a = login(client, state, "a")
    response = client.get("/auth/github/start", follow_redirects=False)
    value = parse_qs(urlsplit(response.headers["location"]).query)["state"][0]
    assert response.status_code == 303
    login(client, state, "b")
    assert (
        client.get(
            "/auth/github/callback",
            params={"state": value, "code": "code"},
            follow_redirects=False,
        ).status_code
        == 400
    )
    client.cookies.set(SESSION_COOKIE, a)
    assert (
        client.get(
            "/auth/github/callback",
            params={"state": value, "code": "code", "installation_id": "1234"},
            follow_redirects=False,
        ).status_code
        == 303
    )
    assert (
        client.get(
            "/auth/github/callback",
            params={"state": value, "code": "code"},
            follow_redirects=False,
        ).status_code
        == 400
    )
    assert github["exchanges"] == 1
    assert client.get("/auth/github").json()["installations"][0]["id"] == 99
    with ledger.db.read() as db:
        rows = db.execute("SELECT token_ciphertext FROM github_connections").fetchall()
        assert b"github-secret" not in rows[0][0]
    body = b'{"action":"revoked","sender":{"id":42}}'
    headers = {
        "X-GitHub-Event": "github_app_authorization",
        "X-GitHub-Delivery": "00000000-0000-0000-0000-000000000001",
        "X-Hub-Signature-256": "sha256="
        + hmac.new(b"webhook-secret", body, hashlib.sha256).hexdigest(),
    }
    assert (
        client.post(
            "/webhooks/github",
            content=body,
            headers={**headers, "X-Hub-Signature-256": "forged"},
        ).status_code
        == 401
    )
    assert client.post("/webhooks/github", content=body, headers=headers).json() == {
        "applied": True
    }
    assert client.post("/webhooks/github", content=body, headers=headers).json() == {
        "applied": False
    }
    assert client.get("/auth/github").json()["status"] == "revoked"
    with sqlite3.connect(checkpoints.snapshot) as durable_db:
        assert durable_db.execute(
            "SELECT delivery_id FROM github_webhook_deliveries"
        ).fetchone()
    # Owner is chosen from the cookie even when the request forges it.
    response = client.post(
        "/tasks",
        headers={"Origin": "https://app.example"},
        json={
            "prompt": "hello",
            "idempotency_key": "forged-owner",
            "owner_id": "00000000-0000-0000-0000-000000000007",
        },
    )
    assert response.status_code in (201, 422)
    if response.status_code == 201:
        assert response.json()["owner_id"] == asyncio.run(sessions.user(a))["id"]
    assert (
        client.post(
            "/tasks",
            headers={"Origin": "https://app.example"},
            json={
                "prompt": "hello",
                "idempotency_key": "forged-repo",
                "repository": "other/private",
                "base_ref": "main",
            },
        ).status_code
        == 422
    )


def test_failed_checkpoint_sanitizes_http_and_readiness_then_recovers(runtime):
    client, state, _, checkpoints, ledger, _ = runtime
    login(client, state, "a")
    state["fail"] = True
    response = client.post(
        "/tasks",
        headers={"Origin": "https://app.example"},
        json={"prompt": "hello", "idempotency_key": "durable"},
    )
    assert response.status_code == 503 and "private" not in response.text
    ready = client.get("/ready", headers={"X-API-Key": "operator"})
    assert ready.status_code == 503 and ready.json()["persistence_error"] == "OSError"
    assert len(ledger.list()) == 1
    state["fail"] = False
    response = client.post(
        "/tasks",
        headers={"Origin": "https://app.example"},
        json={"prompt": "hello", "idempotency_key": "durable"},
    )
    assert response.status_code == 200 and len(ledger.list()) == 1
    assert client.get("/ready", headers={"X-API-Key": "operator"}).status_code == 200


def test_default_lifespan_restores_snapshot_and_uses_one_database(
    runtime, tmp_path, monkeypatch
):
    client, state, _, checkpoints, _, _ = runtime
    cookie = login(client, state, "a")
    snapshot = tmp_path / "startup.snapshot"
    snapshot.write_bytes(checkpoints.snapshot.read_bytes())
    monkeypatch.setenv("GG_RUNTIME_DB_PATH", str(tmp_path / "restored.db"))
    monkeypatch.setenv("GG_RUNTIME_SNAPSHOT_PATH", str(snapshot))
    settings = client.app.state.settings.model_copy(
        update={"dispatch_lock_path": str(tmp_path / "restored.lock")}
    )
    app = create_app(settings)
    assert not hasattr(app.state, "task_ledger")
    with TestClient(app, base_url=settings.web_origin) as restored:
        restored.cookies.set(SESSION_COOKIE, cookie)
        assert restored.get("/auth/session").status_code == 200
        assert app.state.web_sessions.db is app.state.task_ledger.db
        assert app.state.web_sessions.checkpoints is app.state.checkpoints
    assert app.state.task_ledger.db._closed


def test_single_task_and_list_preserve_archived_agent_outcome(runtime):
    from gg.sdk.task_execution import AgentOutcome, TaskResultManifest

    client, state, _, checkpoints, ledger, _ = runtime
    login(client, state, "a")
    response = client.post(
        "/tasks",
        headers={"Origin": "https://app.example"},
        json={"prompt": "hello", "idempotency_key": "result"},
    )
    task = response.json()
    manifest = TaskResultManifest(
        task_id=task["id"],
        execution_id="run",
        repository=None,
        task_branch="gg/task/" + task["id"],
        base_ref=None,
        base_sha=None,
        head_sha=None,
        agent_outcome=AgentOutcome.SUCCEEDED,
    )
    ledger.archive_task_result(
        task_id=task["id"],
        execution_id="run",
        manifest=manifest,
        evidence_complete=True,
        evidence_detail=None,
    )
    assert client.get("/tasks/" + task["id"]).json()["agent_outcome"] == "succeeded"
    assert client.get("/tasks").json()[0]["agent_outcome"] == "succeeded"


@pytest.mark.anyio
async def test_socket_subscribes_before_replay_and_deduplicates(monkeypatch):
    from types import SimpleNamespace

    from gg.runtime import task_routes
    from gg.sdk.domain import Event, EventKind
    from gg.sdk.task_supervision import TaskEventCopy

    first = TaskEventCopy(
        cursor=1,
        source_id="source",
        source_seq=1,
        event=Event(seq=1, kind=EventKind.MESSAGE, payload={"text": "first"}),
    )
    second = first.model_copy(update={"cursor": 2, "source_seq": 2})
    queue = asyncio.Queue()
    state = {"subscribed": False, "unsubscribed": False}

    class Supervision:
        def subscribe_events(self, task_id):
            state["subscribed"] = True
            return queue

        def list_event_copies(self, task_id, after_cursor):
            assert state["subscribed"]
            return [first]

        def unsubscribe_events(self, task_id, target):
            assert target is queue
            state["unsubscribed"] = True

    class Socket:
        app = SimpleNamespace(
            state=SimpleNamespace(
                task_supervision=Supervision(),
                task_service=SimpleNamespace(get=lambda *args, **kwargs: True),
            )
        )
        sent = []

        async def accept(self):
            pass

        async def send_json(self, data):
            self.sent.append(data["cursor"])
            if data["cursor"] == 1:
                queue.put_nowait(first)  # Replay/live overlap.
                queue.put_nowait(second)  # Event during replay send.
            else:
                raise WebSocketDisconnect()

    async def owner(socket):
        return "a"

    monkeypatch.setattr(task_routes, "socket_owner", owner)
    socket = Socket()
    await task_routes.stream_task_events(socket, "task", after=0)
    assert socket.sent == [1, 2] and state["unsubscribed"]


def test_read_routes_do_not_wait_for_unrelated_pending_writes(runtime):
    client, state, sessions, checkpoints, ledger, _ = runtime
    token = login(client, state, "reader")
    created = client.post(
        "/tasks",
        headers={"Origin": "https://app.example"},
        json={"prompt": "hello", "idempotency_key": "reads"},
    ).json()
    task_id = created["id"]
    client.portal.call(client.app.state.task_scheduler.stop)
    with ledger.db.write() as tx:
        tx.connection.execute("CREATE TABLE unrelated_read_test (value TEXT)")
    try:
        state["fail"] = True
        commits = state["commits"]
        for path in (
            "/auth/session",
            "/tasks",
            f"/tasks/{task_id}",
            f"/tasks/{task_id}/events",
            f"/tasks/{task_id}/result",
        ):
            assert client.get(path).status_code == 200
        assert state["commits"] == commits and checkpoints.pending
        client.cookies.set(SESSION_COOKIE, "invalid")
        assert client.get("/tasks").status_code == 401
        assert state["commits"] == commits
        client.cookies.set(SESSION_COOKIE, token)
        response = client.post(
            "/tasks",
            headers={"Origin": "https://app.example"},
            json={"prompt": "blocked mutation", "idempotency_key": "blocked"},
        )
        assert response.status_code == 503 and len(ledger.list()) == 1
    finally:
        state["fail"] = False  # Fixture shutdown must be able to checkpoint.
