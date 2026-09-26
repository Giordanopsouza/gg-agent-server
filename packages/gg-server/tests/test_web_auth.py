"""Supabase Auth browser contract through the runtime HTTP app."""

from __future__ import annotations

import time
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from joserfc import jwk, jwt
from pydantic import ValidationError

from gg.runtime.app import create_app
from gg.runtime.config import RuntimeSettings
from gg.runtime.web_auth import SupabaseAuth


USER_ID = "d23bfe09-a12b-49c5-845f-315fc9ec10d6"


@pytest.fixture
def auth_app(tmp_path):
    settings = RuntimeSettings(
        api_key="operator-secret",
        task_db_path=str(tmp_path / "tasks.sqlite"),
        supabase_url="https://project.supabase.co",
        supabase_publishable_key="publishable-key",
        web_cookie_key=Fernet.generate_key().decode(),
        web_origin="https://app.example",
        task_dispatch_enabled=False,
    )
    key = jwk.ECKey.generate_key("P-256", auto_kid=True)
    state: dict[str, object] = {
        "claims": {},
        "logout": 0,
        "refresh": 0,
        "banned": False,
        "logout_first_401": False,
    }

    def access_token() -> str:
        now = int(time.time())
        return jwt.encode(
            {"alg": "ES256", "kid": key.kid},
            {
                "iss": "https://project.supabase.co/auth/v1",
                "aud": "authenticated",
                "role": "authenticated",
                "sub": USER_ID,
                "session_id": "75945e5b-9b85-4167-8dc7-ae7ce12276a3",
                "iat": now,
                "exp": now + 300,
                **state["claims"],
            },
            key,
            algorithms=["ES256"],
        )

    def provider_response(request: httpx.Request) -> httpx.Response:
        assert request.headers["apikey"] == "publishable-key"
        if request.url.path == "/auth/v1/token":
            if request.url.params["grant_type"] == "refresh_token":
                state["refresh"] += 1
            else:
                assert request.url.params["grant_type"] == "pkce"
                assert request.headers["content-type"] == "application/json"
            return httpx.Response(
                200,
                json={
                    "access_token": access_token(),
                    "refresh_token": "refresh-secret",
                },
            )
        if request.url.path == "/auth/v1/.well-known/jwks.json":
            return httpx.Response(200, json={"keys": [key.as_dict(private=False)]})
        if request.url.path == "/auth/v1/user":
            return httpx.Response(
                200,
                json={
                    "id": USER_ID,
                    "email": "person@example.com",
                    "banned_until": "tomorrow" if state["banned"] else None,
                },
            )
        if request.url.path == "/auth/v1/logout":
            state["logout"] += 1
            if state["logout_first_401"] and state["logout"] == 1:
                return httpx.Response(401)
            return httpx.Response(204)
        raise AssertionError(f"unexpected provider request: {request.url}")

    provider = SupabaseAuth(settings, transport=httpx.MockTransport(provider_response))
    state["provider"] = provider
    state["access_token"] = access_token
    app = create_app(settings, web_auth=provider)
    with TestClient(app, base_url="https://app.example") as client:
        yield client, settings, state


def _start(client: TestClient, return_to: str = "/tasks") -> str:
    response = client.get(
        "/auth/google/start", params={"return_to": return_to}, follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"].startswith(
        "https://project.supabase.co/auth/v1/authorize?"
    )
    params = parse_qs(urlsplit(response.headers["location"]).query)
    assert params["provider"] == ["google"]
    assert params["code_challenge_method"] == ["s256"]
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "Secure" in response.headers["set-cookie"]
    return parse_qs(urlsplit(params["redirect_to"][0]).query)["state"][0]


def _callback(client: TestClient, state: str) -> httpx.Response:
    return client.get(
        "/auth/google/callback",
        params={"state": state, "code": "auth-code"},
        follow_redirects=False,
    )


def test_login_session_and_operator_boundary(auth_app):
    client, _, _ = auth_app
    response = _callback(client, _start(client))
    assert response.status_code == 303
    assert response.headers["location"] == "/tasks"
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "Secure" in response.headers["set-cookie"]
    assert "SameSite=lax" in response.headers["set-cookie"]
    assert "refresh-secret" not in response.headers["set-cookie"]
    session = client.get("/auth/session")
    assert session.status_code == 200
    assert session.json() == {"user": {"id": USER_ID, "email": "person@example.com"}}
    assert client.get("/tasks").status_code == 401
    assert client.post("/tasks", json={"prompt": "example"}).status_code == 401


@pytest.mark.parametrize(
    "claims",
    [
        {"iss": "https://other.example/auth/v1"},
        {"aud": "other"},
        {"exp": 1},
        {"sub": str(UUID(int=1))},
    ],
)
def test_rejects_invalid_access_token(auth_app, claims):
    client, _, state = auth_app
    state["claims"] = claims
    assert _callback(client, _start(client)).status_code == 400
    assert client.get("/auth/session").status_code == 401


def test_rejects_forged_replayed_and_cancelled_callback(auth_app):
    client, _, _ = auth_app
    assert (
        client.get(
            "/auth/google/start", params={"return_to": "//evil.example"}
        ).status_code
        == 400
    )
    state = _start(client)
    assert _callback(client, "forged").status_code == 400
    response = client.get(
        "/auth/google/callback",
        params={"state": state, "error": "access_denied"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/?auth=cancelled"
    assert _callback(client, state).status_code == 400


def test_logout_origin_expiry_and_disabled_account(auth_app):
    client, settings, state = auth_app
    assert _callback(client, _start(client)).status_code == 303
    assert (
        client.post(
            "/auth/logout", headers={"Origin": "https://evil.example"}
        ).status_code
        == 403
    )
    assert client.get("/auth/session").status_code == 200
    state["banned"] = True
    assert client.get("/auth/session").status_code == 401
    state["banned"] = False
    assert (
        client.post("/auth/logout", headers={"Origin": settings.web_origin}).status_code
        == 200
    )
    assert state["logout"] == 1
    assert client.get("/auth/session").status_code == 401


def test_invalid_cookie_does_not_authorize(auth_app):
    client, _, _ = auth_app
    client.cookies.set("gg_session", "forged")
    assert client.get("/auth/session").status_code == 401


def test_expired_access_refreshes_once_for_stale_parallel_cookies(auth_app):
    client, _, state = auth_app
    assert _callback(client, _start(client)).status_code == 303
    state["claims"] = {"exp": 1}
    expired = state["provider"].seal(
        {"access": state["access_token"](), "refresh": "refresh-secret"}
    )
    state["claims"] = {}
    client.cookies.set("gg_session", expired)
    assert client.get("/auth/session").status_code == 200
    client.cookies.set("gg_session", expired)
    assert client.get("/auth/session").status_code == 200
    assert state["refresh"] == 1


def test_web_configuration_requires_safe_origin_and_cookie_key():
    with pytest.raises(ValidationError):
        RuntimeSettings(api_key="operator", web_origin="http://localhost.evil.example")
    with pytest.raises(ValidationError):
        RuntimeSettings(api_key="operator", web_cookie_key="weak")
    with pytest.raises(ValidationError):
        RuntimeSettings(
            api_key="operator",
            web_origin="https://app.example",
            web_cookie_secure=False,
        )


def test_logout_refreshes_expired_access_before_revocation(auth_app):
    client, settings, state = auth_app
    assert _callback(client, _start(client)).status_code == 303
    state["logout_first_401"] = True
    assert (
        client.post("/auth/logout", headers={"Origin": settings.web_origin}).status_code
        == 200
    )
    assert state["refresh"] == 1
    assert state["logout"] == 2
    assert client.get("/auth/session").status_code == 401
