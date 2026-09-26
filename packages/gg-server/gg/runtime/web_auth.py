"""Browser login through Supabase Auth, isolated from the operator API key."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import secrets
import time
from typing import Any
from urllib.parse import urlencode, urlsplit
from uuid import UUID

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from joserfc import jwk, jwt

from gg.runtime.config import RuntimeSettings


SESSION_COOKIE = "gg_session"
FLOW_COOKIE = "gg_login_flow"
FLOW_SECONDS = 600
SESSION_SECONDS = 7 * 24 * 60 * 60


def _safe_return_path(value: str) -> str:
    parsed = urlsplit(value)
    if (
        not value.startswith("/")
        or value.startswith("//")
        or "\\" in value
        or any(ord(char) < 32 for char in value)
        or parsed.scheme
        or parsed.netloc
        or parsed.fragment
    ):
        raise HTTPException(status_code=400, detail="invalid return path")
    return value


def _require_origin(request: Request, settings: RuntimeSettings) -> None:
    if request.headers.get("origin") != settings.web_origin:
        raise HTTPException(status_code=403, detail="invalid origin")


def _configured(settings: RuntimeSettings) -> None:
    if not all(
        (
            settings.supabase_url,
            settings.supabase_publishable_key,
            settings.web_cookie_key,
            settings.web_origin,
        )
    ):
        raise HTTPException(status_code=503, detail="web login is not configured")


class SupabaseAuth:
    """Small GoTrue HTTP client; no Supabase secret key is sent to the browser."""

    def __init__(
        self,
        settings: RuntimeSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self.transport = transport
        self._refresh_lock = asyncio.Lock()
        self._recent_refresh: tuple[float, str, dict[str, Any]] | None = None
        self._cipher = (
            Fernet(settings.web_cookie_key) if settings.web_cookie_key else None
        )

    def seal(self, value: dict[str, Any]) -> str:
        assert self._cipher is not None
        return self._cipher.encrypt(
            json.dumps(value, separators=(",", ":")).encode()
        ).decode()

    def open(self, value: str, *, ttl: int) -> dict[str, Any] | None:
        if self._cipher is None or not value:
            return None
        try:
            payload = json.loads(self._cipher.decrypt(value.encode(), ttl=ttl))
        except (InvalidToken, ValueError, TypeError):
            return None
        return payload if isinstance(payload, dict) else None

    def authorization_url(self, state: str, verifier: str) -> str:
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        callback = (
            f"{self.settings.web_origin}/auth/google/callback?"
            f"{urlencode({'state': state})}"
        )
        query = urlencode(
            {
                "provider": "google",
                "redirect_to": callback,
                "code_challenge": challenge,
                "code_challenge_method": "s256",
            }
        )
        return f"{self.settings.supabase_url}/auth/v1/authorize?{query}"

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.settings.supabase_url,
            transport=self.transport,
            timeout=10,
            headers={"apikey": self.settings.supabase_publishable_key or ""},
        )

    async def exchange(self, code: str, verifier: str) -> dict[str, Any]:
        async with self._client() as client:
            response = await client.post(
                "/auth/v1/token",
                params={"grant_type": "pkce"},
                json={"auth_code": code, "code_verifier": verifier},
            )
            response.raise_for_status()
            return response.json()

    async def refresh(self, refresh_token: str) -> dict[str, Any]:
        async with self._refresh_lock, self._client() as client:
            recent = self._recent_refresh
            if (
                recent is not None
                and time.monotonic() - recent[0] < 10
                and secrets.compare_digest(refresh_token, recent[1])
            ):
                return recent[2]
            response = await client.post(
                "/auth/v1/token",
                params={"grant_type": "refresh_token"},
                json={"refresh_token": refresh_token},
            )
            response.raise_for_status()
            tokens = response.json()
            self._recent_refresh = (time.monotonic(), refresh_token, tokens)
            return tokens

    async def verified_user(self, access_token: str) -> dict[str, str | None]:
        async with self._client() as client:
            keys_response = await client.get("/auth/v1/.well-known/jwks.json")
            keys_response.raise_for_status()
            keys = jwk.KeySet.import_key_set(keys_response.json())
            verified = jwt.decode(access_token, keys, algorithms=["ES256", "RS256"])
            claims = verified.claims
            now = int(time.time())
            if (
                claims.get("iss") != f"{self.settings.supabase_url}/auth/v1"
                or claims.get("aud") != "authenticated"
                or type(claims.get("exp")) is not int
                or claims["exp"] <= now
                or claims.get("role") != "authenticated"
            ):
                raise ValueError("invalid access token claims")
            subject = str(UUID(claims["sub"]))
            UUID(claims["session_id"])
            user_response = await client.get(
                "/auth/v1/user", headers={"Authorization": f"Bearer {access_token}"}
            )
            user_response.raise_for_status()
            user = user_response.json()
            if user.get("id") != subject or user.get("banned_until"):
                raise ValueError("inactive user")
            return {"id": subject, "email": user.get("email")}

    async def sign_out(self, access_token: str) -> None:
        async with self._client() as client:
            response = await client.post(
                "/auth/v1/logout",
                params={"scope": "local"},
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()


def web_auth_router(settings: RuntimeSettings, provider: SupabaseAuth) -> APIRouter:
    router = APIRouter(prefix="/auth")

    @router.get("/google/start")
    def start(return_to: str = "/") -> RedirectResponse:
        _configured(settings)
        state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
        flow = provider.seal(
            {
                "state": state,
                "verifier": verifier,
                "return_to": _safe_return_path(return_to),
            }
        )
        response = RedirectResponse(
            provider.authorization_url(state, verifier), status_code=303
        )
        response.headers["Cache-Control"] = "no-store"
        response.set_cookie(
            FLOW_COOKIE,
            flow,
            max_age=FLOW_SECONDS,
            httponly=True,
            secure=settings.web_cookie_secure,
            samesite="lax",
            path="/auth/google",
        )
        return response

    @router.get("/google/callback")
    async def callback(request: Request) -> RedirectResponse:
        _configured(settings)
        flow = provider.open(request.cookies.get(FLOW_COOKIE, ""), ttl=FLOW_SECONDS)
        state = request.query_params.get("state", "")
        if (
            flow is None
            or not state
            or not secrets.compare_digest(state, flow.get("state", ""))
        ):
            raise HTTPException(status_code=400, detail="invalid or expired login")
        if request.query_params.get("error"):
            response = RedirectResponse("/?auth=cancelled", status_code=303)
        else:
            code = request.query_params.get("code")
            if not code:
                raise HTTPException(status_code=400, detail="invalid login callback")
            try:
                tokens = await provider.exchange(code, flow["verifier"])
                await provider.verified_user(tokens["access_token"])
                if not tokens.get("refresh_token"):
                    raise ValueError("missing refresh token")
            except Exception:
                raise HTTPException(
                    status_code=400, detail="invalid login callback"
                ) from None
            response = RedirectResponse(flow["return_to"], status_code=303)
            response.set_cookie(
                SESSION_COOKIE,
                provider.seal(
                    {
                        "access": tokens["access_token"],
                        "refresh": tokens["refresh_token"],
                    }
                ),
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
    async def session(request: Request, response: Response) -> dict[str, Any]:
        _configured(settings)
        response.headers["Cache-Control"] = "no-store"
        payload = provider.open(
            request.cookies.get(SESSION_COOKIE, ""), ttl=SESSION_SECONDS
        )
        if payload is None:
            raise HTTPException(status_code=401, detail="session expired or absent")
        try:
            user = await provider.verified_user(payload["access"])
        except Exception:
            try:
                tokens = await provider.refresh(payload["refresh"])
                user = await provider.verified_user(tokens["access_token"])
                response.set_cookie(
                    SESSION_COOKIE,
                    provider.seal(
                        {
                            "access": tokens["access_token"],
                            "refresh": tokens["refresh_token"],
                        }
                    ),
                    max_age=SESSION_SECONDS,
                    httponly=True,
                    secure=settings.web_cookie_secure,
                    samesite="lax",
                    path="/",
                )
            except Exception:
                raise HTTPException(
                    status_code=401, detail="session expired or absent"
                ) from None
        return {"user": user}

    @router.post("/logout")
    async def logout(request: Request, response: Response) -> dict[str, bool]:
        _configured(settings)
        _require_origin(request, settings)
        response.headers["Cache-Control"] = "no-store"
        payload = provider.open(
            request.cookies.get(SESSION_COOKIE, ""), ttl=SESSION_SECONDS
        )
        if payload is not None:
            try:
                await provider.sign_out(payload["access"])
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != 401:
                    raise HTTPException(
                        status_code=503, detail="logout unavailable"
                    ) from None
                try:
                    tokens = await provider.refresh(payload["refresh"])
                    await provider.sign_out(tokens["access_token"])
                except httpx.HTTPStatusError as refresh_exc:
                    if refresh_exc.response.status_code not in (400, 401):
                        raise HTTPException(
                            status_code=503, detail="logout unavailable"
                        ) from None
                except httpx.HTTPError:
                    raise HTTPException(
                        status_code=503, detail="logout unavailable"
                    ) from None
            except httpx.HTTPError:
                raise HTTPException(
                    status_code=503, detail="logout unavailable"
                ) from None
        response.delete_cookie(SESSION_COOKIE, path="/")
        return {"ok": True}

    return router
