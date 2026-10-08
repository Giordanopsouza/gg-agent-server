"""Direct Google Code+PKCE login candidate; durable one-use browser flows."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import secrets
import sqlite3
import time
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from joserfc import jwk, jwt
from joserfc.errors import InvalidKeyIdError, MissingKeyError

from gg.runtime.config import RuntimeSettings
from gg.runtime.local_sessions import (
    SESSION_SECONDS,
    LocalSessions,
    durable,
    token_hash,
)
from gg.runtime.web_auth import (
    FLOW_COOKIE,
    SESSION_COOKIE,
    _require_origin,
    _safe_return_path,
)


AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
FLOW_SECONDS = 600


class GoogleAuth:
    def __init__(
        self,
        settings: RuntimeSettings,
        sessions: LocalSessions,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.settings = settings
        self.sessions = sessions
        self.client = httpx.AsyncClient(
            transport=transport, timeout=10, follow_redirects=False
        )
        self._keys = None
        self._keys_at = 0.0
        self._unknown_refresh_at = 0.0
        self._keys_lock = asyncio.Lock()
        self._callback_lock = asyncio.Lock()

    async def close(self) -> None:
        await self.client.aclose()

    def configured(self) -> None:
        if not (
            self.settings.google_client_id
            and self.settings.google_client_secret
            and self.settings.web_origin
        ):
            raise HTTPException(status_code=503, detail="web login is not configured")

    @property
    def callback_url(self) -> str:
        return f"{self.settings.web_origin}/auth/google/callback"

    def authorization_url(self, state: str, verifier: str, nonce: str) -> str:
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        return (
            AUTH_URL
            + "?"
            + urlencode(
                {
                    "client_id": self.settings.google_client_id,
                    "redirect_uri": self.callback_url,
                    "response_type": "code",
                    "scope": "openid email",
                    "state": state,
                    "nonce": nonce,
                    "code_challenge": challenge,
                    "code_challenge_method": "S256",
                }
            )
        )

    async def signing_keys(self, *, refresh: bool = False):
        async with self._keys_lock:
            age = time.monotonic() - self._keys_at
            if (
                self._keys is None
                or age >= 600
                or (refresh and time.monotonic() - self._unknown_refresh_at >= 10)
            ):
                if refresh:
                    self._unknown_refresh_at = time.monotonic()
                response = await self.client.get(JWKS_URL)
                response.raise_for_status()
                self._keys = jwk.KeySet.import_key_set(response.json())
                self._keys_at = time.monotonic()
            return self._keys

    async def verified_user(self, id_token: str, nonce: str) -> dict[str, str]:
        keys = await self.signing_keys()
        try:
            verified = jwt.decode(id_token, keys, algorithms=["RS256"])
        except (InvalidKeyIdError, MissingKeyError):
            verified = jwt.decode(
                id_token, await self.signing_keys(refresh=True), algorithms=["RS256"]
            )
        claims = verified.claims
        audience = claims.get("aud")
        client_id = self.settings.google_client_id
        if (
            claims.get("iss")
            not in ("https://accounts.google.com", "accounts.google.com")
            or not (
                audience == client_id
                or isinstance(audience, list)
                and client_id in audience
            )
            or (
                isinstance(audience, list)
                and len(audience) > 1
                and claims.get("azp") != client_id
            )
            or ("azp" in claims and claims["azp"] != client_id)
            or type(claims.get("exp")) is not int
            or claims["exp"] <= int(time.time())
            or not isinstance(claims.get("nonce"), str)
            or not secrets.compare_digest(claims["nonce"], nonce)
            or claims.get("email_verified") is not True
            or not isinstance(claims.get("sub"), str)
            or not claims["sub"]
            or not isinstance(claims.get("email"), str)
            or not claims["email"]
        ):
            raise ValueError("invalid Google identity claims")
        return {"sub": claims["sub"], "email": claims["email"]}

    async def start(self, return_to: str) -> tuple[str, str]:
        self.configured()
        return_to = _safe_return_path(return_to)
        state, browser, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(4))
        with self.sessions.db.write() as tx:
            tx.connection.execute(
                "INSERT INTO "
                "google_flows(state,browser_hash,nonce,verifier,"
                "return_to,expires_at,status) "
                "VALUES (?, ?, ?, ?, ?, ?, 'pending')",
                (
                    state,
                    token_hash(browser),
                    nonce,
                    verifier,
                    return_to,
                    int(time.time()) + FLOW_SECONDS,
                ),
            )
        await durable(self.sessions.checkpoints, tx.revision)
        return self.authorization_url(state, verifier, nonce), browser

    async def callback(
        self, state: str, browser: str, code: str | None, error: str | None
    ) -> tuple[str, str | None]:
        self.configured()
        # One runtime writer, with SQLite claim as the cross-connection guard.
        async with self._callback_lock:
            with self.sessions.db.read() as connection:
                connection.row_factory = sqlite3.Row
                flow = connection.execute(
                    "SELECT * FROM google_flows WHERE state = ?", (state,)
                ).fetchone()
            if (
                flow is None
                or not browser
                or not secrets.compare_digest(flow["browser_hash"], token_hash(browser))
                or flow["expires_at"] <= int(time.time())
            ):
                raise HTTPException(status_code=400, detail="invalid or expired login")
            # Recover the same opaque session only for an unconfirmed completion.
            token = hmac.new(
                browser.encode(), ("gg-session:" + state).encode(), hashlib.sha256
            ).hexdigest()
            if flow["status"] == "completed":
                if (
                    self.sessions.checkpoints.confirmed_revision
                    >= flow["completion_revision"]
                    or flow["completion_revision"] <= self.sessions.startup_revision
                ):
                    raise HTTPException(
                        status_code=400, detail="login already consumed"
                    )
                await durable(self.sessions.checkpoints, flow["completion_revision"])
                await self.sessions.user(token)
                return flow["return_to"], token
            if flow["status"] != "pending":
                # An interrupted exchange cannot safely reuse Google's one-use code.
                await durable(self.sessions.checkpoints, self.sessions.db.revision)
                raise HTTPException(
                    status_code=400, detail="login already consumed; start again"
                )
            with self.sessions.db.write() as tx:
                claimed = tx.connection.execute(
                    "UPDATE google_flows SET status = 'claimed' WHERE state = ? AND "
                    "status = 'pending'",
                    (state,),
                ).rowcount
            if not claimed:
                raise HTTPException(status_code=400, detail="login already consumed")
            await durable(self.sessions.checkpoints, tx.revision)
            user = None
            if code and not error:
                try:
                    response = await self.client.post(
                        TOKEN_URL,
                        data={
                            "client_id": self.settings.google_client_id,
                            "client_secret": self.settings.google_client_secret,
                            "redirect_uri": self.callback_url,
                            "grant_type": "authorization_code",
                            "code": code,
                            "code_verifier": flow["verifier"],
                        },
                    )
                    response.raise_for_status()
                    user = await self.verified_user(
                        response.json()["id_token"], flow["nonce"]
                    )
                except Exception:
                    pass  # No tokens or provider bodies enter logs/responses.
            with self.sessions.db.write() as tx:
                if user is not None:
                    self.sessions.insert(
                        tx.connection, user["sub"], user["email"], token
                    )
                revision = (
                    tx.connection.execute(
                        "SELECT revision FROM runtime_metadata"
                    ).fetchone()[0]
                    + 1
                )
                tx.connection.execute(
                    "UPDATE google_flows SET status = ?, session_hash = ?, "
                    "completion_revision = ?, verifier = '' "
                    "WHERE state = ?",
                    (
                        "completed" if user else "failed",
                        token_hash(token) if user else None,
                        revision,
                        state,
                    ),
                )
            await durable(self.sessions.checkpoints, tx.revision)
            if user is None:
                return "/?auth=cancelled" if error else "/?auth=failed", None
            return flow["return_to"], token


def google_auth_router(
    settings: RuntimeSettings, provider: GoogleAuth, sessions: LocalSessions
) -> APIRouter:
    if provider.sessions is not sessions or provider.settings != settings:
        raise ValueError("Google provider must share settings and sessions")
    router = APIRouter(prefix="/auth")

    @router.get("/google/start")
    async def start(return_to: str = "/"):
        try:
            url, browser = await provider.start(return_to)
        except sqlite3.Error:
            raise HTTPException(
                status_code=503, detail="session store unavailable"
            ) from None
        response = RedirectResponse(url, status_code=303)
        response.headers["Cache-Control"] = "no-store"
        response.set_cookie(
            FLOW_COOKIE,
            browser,
            max_age=FLOW_SECONDS,
            httponly=True,
            secure=settings.web_cookie_secure,
            samesite="lax",
            path="/auth/google",
        )
        return response

    @router.get("/google/callback")
    async def callback(request: Request):
        try:
            path, token = await provider.callback(
                request.query_params.get("state", ""),
                request.cookies.get(FLOW_COOKIE, ""),
                request.query_params.get("code"),
                request.query_params.get("error"),
            )
        except sqlite3.Error:
            raise HTTPException(
                status_code=503, detail="session store unavailable"
            ) from None
        response = RedirectResponse(path, status_code=303)
        if token:
            response.set_cookie(
                SESSION_COOKIE,
                token,
                max_age=SESSION_SECONDS,
                httponly=True,
                secure=settings.web_cookie_secure,
                samesite="lax",
                path="/",
            )
        response.delete_cookie(FLOW_COOKIE, path="/auth/google")
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @router.get("/session")
    async def session(request: Request, response: Response):
        provider.configured()
        response.headers["Cache-Control"] = "no-store"
        try:
            return {
                "user": await sessions.user(request.cookies.get(SESSION_COOKIE, ""))
            }
        except sqlite3.Error:
            raise HTTPException(
                status_code=503, detail="session store unavailable"
            ) from None

    @router.post("/logout")
    async def logout(request: Request, response: Response):
        provider.configured()
        _require_origin(request, settings)
        try:
            await sessions.revoke(request.cookies.get(SESSION_COOKIE, ""))
        except sqlite3.Error:
            raise HTTPException(
                status_code=503, detail="session store unavailable"
            ) from None
        response.delete_cookie(SESSION_COOKIE, path="/")
        response.headers["Cache-Control"] = "no-store"
        return {"ok": True}

    return router
