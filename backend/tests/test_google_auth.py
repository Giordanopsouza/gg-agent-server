"""Direct OIDC HTTP callbacks with controlled RSA tokens and SQLite snapshots."""

import asyncio
import base64
import hashlib
import time
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from joserfc import jwk, jwt
from joserfc.errors import BadSignatureError

from gg.runtime.checkpoints import CheckpointCoordinator
from gg.runtime.config import RuntimeSettings, load_settings
from gg.runtime.google_auth import GoogleAuth, google_auth_router
from gg.runtime.local_sessions import LocalSessions
from gg.runtime.sqlite_db import SQLiteDB, initialize


@pytest.fixture
def google_app(tmp_path):
    initialize(tmp_path / "db")
    db = SQLiteDB(tmp_path / "db")
    settings = RuntimeSettings(
        api_key="operator",
        google_client_id="google-client",
        google_client_secret="google-secret",
        web_origin="https://app.example",
    )
    state = {
        "claims": {},
        "exchanges": 0,
        "jwks": 0,
        "fail": False,
        "fail_at": None,
        "commits": 0,
        "nonce": "",
        "verifier": None,
        "key": jwk.RSAKey.generate_key(2048, auto_kid=True),
    }

    async def commit():
        state["commits"] += 1
        if state["fail"] or state["commits"] == state["fail_at"]:
            raise OSError("private snapshot error")

    checkpoints = CheckpointCoordinator(db, tmp_path / "snapshot", commit)
    sessions = LocalSessions(db, checkpoints)

    def respond(request):
        if request.url.path == "/oauth2/v3/certs":
            state["jwks"] += 1
            return httpx.Response(
                200, json={"keys": [state["key"].as_dict(private=False)]}
            )
        assert str(request.url) == "https://oauth2.googleapis.com/token"
        form = parse_qs(request.content.decode())
        assert form["redirect_uri"] == ["https://app.example/auth/google/callback"]
        assert form["client_id"] == ["google-client"]
        assert form["client_secret"] == ["google-secret"]
        assert form["grant_type"] == ["authorization_code"]
        state["verifier"] = form["code_verifier"][0]
        state["exchanges"] += 1
        token = jwt.encode(
            {"alg": "RS256", "kid": state["key"].kid},
            {
                "iss": "https://accounts.google.com",
                "aud": "google-client",
                "sub": "google-a",
                "email": "a@example.com",
                "email_verified": True,
                "nonce": state["nonce"],
                "exp": int(time.time()) + 300,
                **state["claims"],
            },
            state["key"],
            algorithms=["RS256"],
        )
        return httpx.Response(200, json={"id_token": token})

    provider = GoogleAuth(settings, sessions, transport=httpx.MockTransport(respond))
    app = FastAPI()
    app.include_router(google_auth_router(settings, provider, sessions))
    with TestClient(app, base_url="https://app.example") as client:
        yield client, settings, state, provider, sessions, checkpoints
    db.close()


def start(client, state, return_to="/tasks"):
    response = client.get(
        "/auth/google/start", params={"return_to": return_to}, follow_redirects=False
    )
    assert response.status_code == 303
    query = parse_qs(urlsplit(response.headers["location"]).query)
    state["nonce"] = query["nonce"][0]
    return query, client.cookies.get("gg_login_flow")


def callback(client, query):
    return client.get(
        "/auth/google/callback",
        params={"state": query["state"][0], "code": "one-use-code"},
        follow_redirects=False,
    )


def test_direct_login_session_logout_and_replay(google_app):
    client, settings, state, provider, sessions, checkpoints = google_app
    query, browser = start(client, state)
    assert query["scope"] == ["openid email"] and query["code_challenge_method"] == [
        "S256"
    ]
    assert "hd" not in query
    assert checkpoints.confirmed_revision == sessions.db.revision
    response = callback(client, query)
    assert response.status_code == 303 and response.headers["location"] == "/tasks"
    assert all(
        flag in response.headers["set-cookie"]
        for flag in ("HttpOnly", "Secure", "SameSite=lax", "Max-Age=604800")
    )
    assert "google-secret" not in response.text
    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(state["verifier"].encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    assert query["code_challenge"] == [expected]
    session = client.get("/auth/session")
    assert (
        session.status_code == 200
        and session.json()["user"]["email"] == "a@example.com"
    )
    calls = state["exchanges"], state["jwks"]
    assert client.get("/auth/session").status_code == 200
    assert calls == (state["exchanges"], state["jwks"])
    client.cookies.set(
        "gg_login_flow", browser, domain="app.example", path="/auth/google"
    )
    assert callback(client, query).status_code == 400
    assert state["exchanges"] == 1
    assert client.post("/auth/logout").status_code == 403
    token = client.cookies.get("gg_session")
    assert (
        client.post("/auth/logout", headers={"Origin": settings.web_origin}).status_code
        == 200
    )
    client.cookies.set("gg_session", token, domain="app.example", path="/")
    assert client.get("/auth/session").status_code == 401


@pytest.mark.parametrize(
    "claims",
    [
        {"iss": "https://evil.example"},
        {"aud": "other"},
        {"exp": 1},
        {"exp": "300"},
        {"nonce": "wrong"},
        {"email_verified": False},
        {"email_verified": "true"},
        {"sub": ""},
        {"sub": 123},
        {"email": None},
        {"azp": "other"},
        {"aud": ["google-client", "other"]},
    ],
)
def test_rejects_invalid_claims(google_app, claims):
    client, _, state, _, _, _ = google_app
    state["claims"] = claims
    response = callback(client, start(client, state)[0])
    assert response.headers["location"] == "/?auth=failed"
    assert client.get("/auth/session").status_code == 401


@pytest.mark.parametrize(
    "return_to",
    [
        "//evil.example",
        "/\\evil",
        "/tasks#fragment",
        "https://evil.example",
        "/\nheader",
    ],
)
def test_safe_redirect(google_app, return_to):
    client = google_app[0]
    assert (
        client.get(
            "/auth/google/start",
            params={"return_to": return_to},
            follow_redirects=False,
        ).status_code
        == 400
    )


def test_browser_binding_expiry_cancel_and_missing_code(google_app):
    client, _, state, _, sessions, _ = google_app
    query, browser = start(client, state)
    client.cookies.clear()
    assert callback(client, query).status_code == 400
    client.cookies.set(
        "gg_login_flow", "forged", domain="app.example", path="/auth/google"
    )
    assert callback(client, query).status_code == 400
    client.cookies.set(
        "gg_login_flow", browser, domain="app.example", path="/auth/google"
    )
    with sessions.db.write() as tx:
        tx.connection.execute("UPDATE google_flows SET expires_at = 1")
    assert callback(client, query).status_code == 400
    for params, expected in [
        ({"error": "access_denied"}, "/?auth=cancelled"),
        ({}, "/?auth=failed"),
    ]:
        query, _ = start(client, state)
        response = client.get(
            "/auth/google/callback",
            params={"state": query["state"][0], **params},
            follow_redirects=False,
        )
        assert response.headers["location"] == expected
    assert state["exchanges"] == 0


@pytest.mark.anyio
async def test_callback_is_consumed_once_across_connections(google_app):
    _, settings, state, provider, sessions, checkpoints = google_app
    url, browser = await provider.start("/tasks")
    query = parse_qs(urlsplit(url).query)
    state["nonce"] = query["nonce"][0]
    second = GoogleAuth(settings, sessions, transport=provider.client._transport)
    outcomes = await asyncio.gather(
        provider.callback(query["state"][0], browser, "code", None),
        second.callback(query["state"][0], browser, "code", None),
        return_exceptions=True,
    )
    assert sum(isinstance(result, tuple) for result in outcomes) == 1
    assert isinstance(
        next(result for result in outcomes if not isinstance(result, tuple)),
        HTTPException,
    )
    assert state["exchanges"] == 1
    with sessions.db.read() as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM local_sessions").fetchone()[0] == 1
        )
    await second.close()


def test_jwks_rotation(google_app):
    client, _, state, provider, _, _ = google_app
    assert callback(client, start(client, state)[0]).headers["location"] == "/tasks"
    state["key"] = jwk.RSAKey.generate_key(2048, auto_kid=True)
    assert callback(client, start(client, state)[0]).headers["location"] == "/tasks"
    assert state["jwks"] == 2


def test_checkpoint_failures_start_callback_and_logout(google_app):
    client, settings, state, _, sessions, checkpoints = google_app
    state["fail"] = True
    assert client.get("/auth/google/start", follow_redirects=False).status_code == 503
    assert "gg_login_flow" not in client.cookies
    state["fail"] = False
    query, _ = start(client, state)
    # Claim barrier succeeds, final profile+session checkpoint fails.
    state["fail_at"] = state["commits"] + 2
    failed = callback(client, query)
    assert failed.status_code == 503 and "gg_session" not in client.cookies
    assert "private" not in failed.text
    assert checkpoints.pending
    state["fail_at"] = None
    assert callback(client, query).status_code == 303
    assert state["exchanges"] == 1
    assert not checkpoints.pending
    state["fail"] = True
    assert (
        client.post("/auth/logout", headers={"Origin": settings.web_origin}).status_code
        == 503
    )
    assert "gg_session" in client.cookies
    state["fail"] = False
    assert (
        client.post("/auth/logout", headers={"Origin": settings.web_origin}).status_code
        == 200
    )


def test_failed_claim_checkpoint_does_not_exchange_again(google_app):
    client, _, state, _, _, _ = google_app
    query, _ = start(client, state)
    state["fail"] = True
    assert callback(client, query).status_code == 503
    assert state["exchanges"] == 0
    state["fail"] = False
    assert callback(client, query).status_code == 400
    assert state["exchanges"] == 0


def test_google_settings_from_environment(monkeypatch):
    monkeypatch.setenv("GG_RUNTIME_API_KEY", "operator")
    monkeypatch.setenv("GG_GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setenv("GG_GOOGLE_CLIENT_SECRET", "client-secret")
    settings = load_settings()
    assert settings.google_client_id == "client-id"
    assert settings.google_client_secret == "client-secret"


@pytest.mark.anyio
async def test_rejects_signature_from_another_key(google_app):
    _, _, _, provider, _, _ = google_app
    attacker = jwk.RSAKey.generate_key(2048)
    key = google_app[2]["key"]
    token = jwt.encode(
        {"alg": "RS256", "kid": key.kid},
        {
            "iss": "https://accounts.google.com",
            "aud": "google-client",
            "sub": "a",
            "email": "a@example.com",
            "email_verified": True,
            "nonce": "expected",
            "exp": int(time.time()) + 300,
        },
        attacker,
        algorithms=["RS256"],
    )
    with pytest.raises(BadSignatureError):
        await provider.verified_user(token, "expected")


@pytest.mark.anyio
async def test_restored_flow_cannot_replay_completed_login(google_app, tmp_path):
    import shutil

    client, settings, state, _, _, checkpoints = google_app
    query, browser = start(client, state)
    assert callback(client, query).status_code == 303
    shutil.copyfile(checkpoints.snapshot, tmp_path / "restored")

    async def commit():
        pass

    with SQLiteDB(tmp_path / "restored") as db:
        sessions = LocalSessions(
            db, CheckpointCoordinator(db, tmp_path / "snapshot2", commit)
        )
        provider = GoogleAuth(settings, sessions)
        with pytest.raises(HTTPException) as error:
            await provider.callback(query["state"][0], browser, "code", None)
        assert error.value.status_code == 400
        await provider.close()
