# ruff: noqa: E501
"""GitHub App connection contract over HTTP with a controlled provider."""

from __future__ import annotations

import hashlib
import hmac
import sqlite3
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient

from gg.runtime.config import RuntimeSettings
from gg.runtime.github_connection import GitHubClient, github_connection_router
from gg.runtime.local_sessions import LocalSessions
from gg.runtime.web_auth import SESSION_COOKIE


class FakeSessions(LocalSessions):
    def __init__(self):
        pass

    async def user(self, token):
        return {"id": token, "email": "same@example.test"}


class FakeStore:
    def __init__(self):
        self.flows = set()
        self.accounts = {}
        self.deliveries = set()

    def begin(self, owner, session, state):
        self.flows.add((owner, session, state))

    def consume(self, owner, session, state):
        item = (owner, session, state)
        if item not in self.flows:
            return False
        self.flows.remove(item)
        return True

    def connect(self, owner, github_id, login, token, installations):
        for other, record in self.accounts.items():
            if other != owner and record[0] == github_id:
                raise sqlite3.IntegrityError("unique GitHub user")
        self.accounts[owner] = (github_id, login, token, "connected", installations)

    def current(self, owner):
        record = self.accounts.get(owner)
        return record[:4] if record else None

    def refresh(self, owner, github_id, installations):
        record = self.accounts[owner]
        self.accounts[owner] = (
            github_id,
            record[1],
            record[2],
            "connected" if installations else "pending",
            installations,
        )
        return {
            "status": self.accounts[owner][3],
            "login": record[1],
            "installations": installations,
        }

    def mark_revoked(self, owner):
        record = self.accounts[owner]
        self.accounts[owner] = (*record[:3], "revoked", [])

    def disconnect(self, owner):
        self.accounts.pop(owner, None)

    def webhook(self, delivery, event, action, installation_id, github_id):
        if delivery in self.deliveries:
            return False
        self.deliveries.add(delivery)
        if event == "installation" and action == "deleted":
            for owner, record in list(self.accounts.items()):
                installations = [
                    item for item in record[4] if item["id"] != installation_id
                ]
                self.accounts[owner] = (*record[:4], installations)
        if event == "github_app_authorization" and action == "revoked":
            for owner, record in list(self.accounts.items()):
                if record[0] == github_id:
                    self.mark_revoked(owner)
        return True


def fixture():
    settings = RuntimeSettings(
        api_key="operator",
        web_origin="https://app.example",
        web_cookie_key=Fernet.generate_key().decode(),
        github_app_client_id="Iv1.client",
        github_app_client_secret="client-secret",
        github_webhook_secret="webhook-secret",
    )
    state = {
        "github_id": 42,
        "installations": [
            {"id": 99, "account": {"login": "org", "type": "Organization"}}
        ],
        "unauthorized": False,
    }

    def github_response(request):
        if request.url.path == "/login/oauth/access_token":
            assert request.headers["Accept"] == "application/json"
            assert request.content.find(b"client-secret") >= 0
            return httpx.Response(200, json={"access_token": "secret-github-token"})
        assert request.headers["Authorization"] == "Bearer secret-github-token"
        if state["unauthorized"]:
            return httpx.Response(401)
        if request.url.path == "/user":
            return httpx.Response(
                200,
                json={
                    "id": state["github_id"],
                    "login": "alice",
                    "email": "same@example.test",
                },
            )
        if request.url.path == "/user/installations":
            return httpx.Response(200, json={"installations": state["installations"]})
        raise AssertionError(request.url)

    auth = object()
    store = FakeStore()
    app = FastAPI()
    app.include_router(
        github_connection_router(
            settings,
            FakeSessions(),
            store,
            GitHubClient(settings, httpx.MockTransport(github_response)),
        )
    )
    client = TestClient(app, base_url="https://app.example")
    return client, auth, store, state


def as_user(client, auth, owner):
    client.cookies.set(SESSION_COOKIE, owner)


def start(client):
    response = client.get("/auth/github/start", follow_redirects=False)
    assert response.status_code == 303
    params = parse_qs(urlsplit(response.headers["location"]).query)
    assert params["code_challenge_method"] == ["S256"]
    assert "client-secret" not in response.headers["location"]
    return params["state"][0]


def test_callback_binding_installations_disconnect_and_replay():
    client, auth, store, state = fixture()
    a, b = str(uuid4()), str(uuid4())
    as_user(client, auth, a)
    assert client.get("/auth/github").json()["status"] == "disconnected"
    value = start(client)
    assert (
        client.get(
            "/auth/github/callback", params={"state": "forged", "code": "abc"}
        ).status_code
        == 400
    )
    as_user(client, auth, b)
    assert (
        client.get(
            "/auth/github/callback", params={"state": value, "code": "abc"}
        ).status_code
        == 400
    )
    as_user(client, auth, a)
    response = client.get(
        "/auth/github/callback",
        params={"state": value, "code": "abc", "installation_id": "999"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert (
        client.get(
            "/auth/github/callback", params={"state": value, "code": "abc"}
        ).status_code
        == 400
    )
    data = client.get("/auth/github").json()
    assert data == {
        "status": "connected",
        "login": "alice",
        "installations": [
            {"id": 99, "account_login": "org", "account_type": "Organization"}
        ],
    }
    assert "secret-github-token" not in str(data)
    as_user(client, auth, b)
    assert client.get("/auth/github").json()["status"] == "disconnected"
    other_state = start(client)
    assert (
        client.get(
            "/auth/github/callback", params={"state": other_state, "code": "abc"}
        ).status_code
        == 409
    )
    assert client.delete("/auth/github").status_code == 403
    assert (
        client.delete(
            "/auth/github", headers={"Origin": "https://app.example"}
        ).status_code
        == 200
    )
    as_user(client, auth, a)
    assert (
        client.delete(
            "/auth/github", headers={"Origin": "https://app.example"}
        ).status_code
        == 200
    )
    assert client.get("/auth/github").json()["status"] == "disconnected"
    assert not store.accounts


def test_pending_revocation_and_signed_webhook():
    client, auth, store, state = fixture()
    owner = str(uuid4())
    as_user(client, auth, owner)
    state["installations"] = []
    value = start(client)
    assert (
        client.get(
            "/auth/github/callback",
            params={"state": value, "code": "abc"},
            follow_redirects=False,
        ).status_code
        == 303
    )
    assert client.get("/auth/github").json()["status"] == "pending"
    state["installations"] = [
        {"id": 99, "account": {"login": "org", "type": "Organization"}}
    ]
    assert client.get("/auth/github").json()["status"] == "connected"
    state["installations"] = [
        {
            "id": 99,
            "account": {"login": "org", "type": "Organization"},
            "suspended_at": "2026-09-28T00:00:00Z",
        }
    ]
    assert client.get("/auth/github").json()["status"] == "pending"
    state["installations"] = [
        {"id": 99, "account": {"login": "org", "type": "Organization"}}
    ]
    body = b'{"action":"deleted","installation":{"id":99}}'
    headers = {
        "X-GitHub-Event": "installation",
        "X-GitHub-Delivery": str(uuid4()),
        "X-Hub-Signature-256": "sha256="
        + hmac.new(b"webhook-secret", body, hashlib.sha256).hexdigest(),
    }
    assert (
        client.post(
            "/webhooks/github",
            content=body,
            headers={**headers, "X-Hub-Signature-256": "sha256=invalid"},
        ).status_code
        == 401
    )
    assert client.post("/webhooks/github", content=body, headers=headers).json() == {
        "applied": True
    }
    assert client.post("/webhooks/github", content=body, headers=headers).json() == {
        "applied": False
    }
    # A late deletion only invalidates the snapshot; a fresh GitHub check restores it.
    assert client.get("/auth/github").json()["installations"][0]["id"] == 99
    state["unauthorized"] = True
    assert client.get("/auth/github").json()["status"] == "revoked"
    assert store.accounts[owner][4] == []


@pytest.mark.anyio
async def test_sqlite_constraints_flow_expiry_webhook_and_snapshot_recovery(tmp_path):
    import shutil
    import sqlite3

    import pytest

    from gg.runtime.checkpoints import CheckpointCoordinator
    from gg.runtime.github_connection import SQLiteGitHubConnections
    from gg.runtime.local_sessions import LocalSessions, token_hash
    from gg.runtime.sqlite_db import SQLiteDB
    from test_support.sqlite_ledger import new_ledger

    flags = {"fail": False}

    async def commit():
        if flags["fail"]:
            raise OSError("private volume error")

    with new_ledger() as ledger:
        db = ledger.db
        checkpoints = CheckpointCoordinator(db, tmp_path / "snapshot", commit)
        sessions = LocalSessions(db, checkpoints)
        a = await sessions.create("a", "a@example.com")
        b = await sessions.create("b", "b@example.com")
        owner_a = (await sessions.user(a))["id"]
        owner_b = (await sessions.user(b))["id"]
        key = Fernet.generate_key().decode()
        store = SQLiteGitHubConnections(db, checkpoints, key)
        store.begin(owner_a, token_hash(a), "flow")
        assert not store.consume(owner_b, token_hash(b), "flow")
        assert not store.consume(owner_a, token_hash(b), "flow")
        assert store.consume(owner_a, token_hash(a), "flow")
        assert not store.consume(owner_a, token_hash(a), "flow")
        store.begin(owner_a, token_hash(a), "expired")
        with db.write() as tx:
            tx.connection.execute("UPDATE github_oauth_flows SET expires_at=1")
        assert not store.consume(owner_a, token_hash(a), "expired")
        installations = [
            {"id": 99, "account_login": "org", "account_type": "Organization"}
        ]
        store.connect(owner_a, 42, "alice", "secret-token", installations)
        revision = db.revision
        with pytest.raises(sqlite3.IntegrityError):
            store.connect(owner_b, 42, "alice", "other-token", installations)
        assert db.revision == revision and store.current(owner_b) is None
        store.connect(owner_b, 43, "bob", "bob-token", installations)
        delivery = uuid4()
        assert store.webhook(delivery, "github_app_authorization", "revoked", None, 42)
        assert not store.webhook(
            delivery, "github_app_authorization", "revoked", None, 42
        )
        assert store.current(owner_a)[2:] == (None, "revoked")
        assert store.current(owner_b)[2] == "bob-token"
        flags["fail"] = True
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as error:
            await store.ensure_durable()
        assert error.value.status_code == 503
        flags["fail"] = False
        await store.ensure_durable()
        shutil.copyfile(checkpoints.snapshot, tmp_path / "restored")
    with SQLiteDB(tmp_path / "restored") as db:
        store = SQLiteGitHubConnections(
            db, CheckpointCoordinator(db, tmp_path / "next", commit), key
        )
        assert not store.webhook(
            delivery, "github_app_authorization", "revoked", None, 42
        )
        assert store.current(owner_b)[2] == "bob-token"
        store.disconnect(owner_b)
        assert store.current(owner_b) is None
        with db.read() as conn:
            assert (
                conn.execute(
                    "SELECT * FROM github_installations WHERE owner_id=?", (owner_b,)
                ).fetchall()
                == []
            )
