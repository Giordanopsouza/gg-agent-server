# ruff: noqa: E501
"""Link a signed-in Supabase user to a verified GitHub App user authorization."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import secrets
import sqlite3
import time
from typing import Any
from urllib.parse import urlencode
from uuid import UUID

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from gg.runtime.checkpoints import CheckpointCoordinator
from gg.runtime.config import RuntimeSettings
from gg.runtime.local_sessions import LocalSessions, durable, token_hash
from gg.runtime.sqlite_db import SQLiteDB
from gg.runtime.web_auth import (
    SESSION_COOKIE,
    SupabaseAuth,
    _require_origin,
    authenticated_web_user,
)


FLOW_COOKIE = "gg_github_flow"
FLOW_SECONDS = 600
NO_STORE = {"Cache-Control": "no-store"}
GITHUB_API = "https://api.github.com"
GITHUB_OAUTH = "https://github.com"


class GitHubUnavailable(Exception):
    pass


class GitHubUnauthorized(Exception):
    pass


class GitHubPending(Exception):
    pass


class GitHubClient:
    def __init__(
        self,
        settings: RuntimeSettings,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self.transport = transport

    @property
    def callback_url(self) -> str:
        return f"{self.settings.web_origin}/auth/github/callback"

    def authorize_url(self, state: str, verifier: str) -> str:
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        return f"{GITHUB_OAUTH}/login/oauth/authorize?" + urlencode(
            {
                "client_id": self.settings.github_app_client_id,
                "redirect_uri": self.callback_url,
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "prompt": "select_account",
            }
        )

    def _client(self, base_url: str) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=base_url,
            transport=self.transport,
            timeout=10,
            follow_redirects=False,
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )

    async def exchange(self, code: str, verifier: str) -> str:
        try:
            async with self._client(GITHUB_OAUTH) as client:
                response = await client.post(
                    "/login/oauth/access_token",
                    headers={"Accept": "application/json"},
                    data={
                        "client_id": self.settings.github_app_client_id,
                        "client_secret": self.settings.github_app_client_secret,
                        "redirect_uri": self.callback_url,
                        "code": code,
                        "code_verifier": verifier,
                    },
                )
            response.raise_for_status()
            payload = response.json()
            token = payload.get("access_token")
            if payload.get("error") or not isinstance(token, str) or not token:
                raise GitHubUnauthorized
            return token
        except (httpx.HTTPError, ValueError) as exc:
            raise GitHubUnavailable from exc

    async def _get(
        self,
        client: httpx.AsyncClient,
        path: str,
        token: str,
        *,
        params: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        try:
            response = await client.get(
                path, params=params, headers={"Authorization": f"Bearer {token}"}
            )
            if response.status_code == 401:
                raise GitHubUnauthorized
            if response.status_code == 403:
                raise GitHubPending
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("invalid GitHub response")
            return payload
        except (httpx.HTTPError, ValueError) as exc:
            raise GitHubUnavailable from exc

    async def identity_and_installations(
        self, token: str
    ) -> tuple[int, str, list[dict[str, Any]]]:
        async with self._client(GITHUB_API) as client:
            user = await self._get(client, "/user", token)
            user_id, login = user.get("id"), user.get("login")
            if (
                type(user_id) is not int
                or user_id <= 0
                or not isinstance(login, str)
                or not login
            ):
                raise GitHubUnavailable
            installations: list[dict[str, Any]] = []
            for page in range(1, 11):
                try:
                    payload = await self._get(
                        client,
                        "/user/installations",
                        token,
                        params={"per_page": 100, "page": page},
                    )
                except GitHubPending:
                    return user_id, login, []
                items = payload.get("installations")
                if not isinstance(items, list):
                    raise GitHubUnavailable
                for item in items:
                    if (
                        not isinstance(item, dict)
                        or type(item.get("id")) is not int
                        or item["id"] <= 0
                    ):
                        raise GitHubUnavailable
                    if item.get("suspended_at") is not None:
                        continue
                    account = item.get("account")
                    if not isinstance(account, dict) or not isinstance(
                        account.get("login"), str
                    ):
                        raise GitHubUnavailable
                    installations.append(
                        {
                            "id": item["id"],
                            "account_login": account["login"],
                            "account_type": str(account.get("type", "")),
                        }
                    )
                if len(items) < 100:
                    return user_id, login, installations
            raise GitHubUnavailable  # Fail closed if pagination exceeds the bounded scan.


class SQLiteGitHubConnections:
    def __init__(
        self, db: SQLiteDB, checkpoints: CheckpointCoordinator, encryption_key: str
    ):
        if checkpoints.db is not db:
            raise ValueError("connections and checkpoints must share a database")
        self.db, self.checkpoints = db, checkpoints
        self.cipher = Fernet(encryption_key)

    async def ensure_durable(self):
        await durable(self.checkpoints, self.db.revision)

    def begin(self, owner_id: str, session_id: str, state: str) -> None:
        with self.db.write() as tx:
            session = tx.connection.execute(
                "SELECT 1 FROM local_sessions WHERE token_hash=? AND owner_id=? "
                "AND revoked=0 AND expires_at>?",
                (session_id, owner_id, int(time.time())),
            ).fetchone()
            if session is None:
                raise HTTPException(status_code=401, detail="session expired or absent")
            tx.connection.execute(
                "INSERT INTO github_oauth_flows VALUES (?, ?, ?, ?)",
                (
                    token_hash(state),
                    owner_id,
                    session_id,
                    int(time.time()) + FLOW_SECONDS,
                ),
            )

    def consume(self, owner_id: str, session_id: str, state: str) -> bool:
        with self.db.write() as tx:
            row = tx.connection.execute(
                "DELETE FROM github_oauth_flows WHERE state_hash = ? AND owner_id = ? "
                "AND session_id = ? AND expires_at > ? AND EXISTS (SELECT 1 FROM "
                "local_sessions s WHERE s.token_hash=github_oauth_flows.session_id "
                "AND s.owner_id=github_oauth_flows.owner_id AND s.revoked=0 "
                "AND s.expires_at>?) RETURNING state_hash",
                (
                    token_hash(state),
                    owner_id,
                    session_id,
                    int(time.time()),
                    int(time.time()),
                ),
            ).fetchone()
        return row is not None

    def connect(
        self,
        owner_id: str,
        github_id: int,
        login: str,
        token: str,
        installations: list[dict[str, Any]],
    ) -> None:
        with self.db.write() as tx:
            tx.connection.execute(
                "INSERT INTO github_connections VALUES (?, ?, ?, ?, ?) ON CONFLICT(owner_id) "
                "DO UPDATE SET github_user_id=excluded.github_user_id, login=excluded.login, "
                "token_ciphertext=excluded.token_ciphertext, status=excluded.status",
                (
                    owner_id,
                    github_id,
                    login,
                    self.cipher.encrypt(token.encode()),
                    "connected" if installations else "pending",
                ),
            )
            self._replace_installations(tx.connection, owner_id, installations)

    def _replace_installations(self, connection, owner_id, installations):
        connection.execute(
            "UPDATE github_installations SET status='removed' WHERE owner_id=?",
            (owner_id,),
        )
        for item in installations:
            connection.execute(
                "INSERT INTO github_installations VALUES (?, ?, ?, ?, 'active') "
                "ON CONFLICT(owner_id,installation_id) DO UPDATE SET "
                "account_login=excluded.account_login,account_type=excluded.account_type,status='active'",
                (owner_id, item["id"], item["account_login"], item["account_type"]),
            )

    def current(self, owner_id: str):
        with self.db.read() as connection:
            row = connection.execute(
                "SELECT github_user_id,login,token_ciphertext,status "
                "FROM github_connections WHERE owner_id=?",
                (owner_id,),
            ).fetchone()
        return (
            (
                row[0],
                row[1],
                self.cipher.decrypt(row[2]).decode() if row[2] else None,
                row[3],
            )
            if row
            else None
        )

    def refresh(
        self, owner_id: str, github_id: int, installations: list[dict[str, Any]]
    ):
        with self.db.write() as tx:
            row = tx.connection.execute(
                "SELECT github_user_id,status,login FROM github_connections WHERE owner_id=?",
                (owner_id,),
            ).fetchone()
            if not row or row[0] != github_id or row[1] == "revoked":
                return {"status": "revoked", "login": None, "installations": []}
            self._replace_installations(tx.connection, owner_id, installations)
            status = "connected" if installations else "pending"
            tx.connection.execute(
                "UPDATE github_connections SET status=? WHERE owner_id=?",
                (status, owner_id),
            )
        return {"status": status, "login": row[2], "installations": installations}

    def mark_revoked(self, owner_id: str):
        with self.db.write() as tx:
            tx.connection.execute(
                "UPDATE github_connections SET status='revoked',token_ciphertext=NULL WHERE owner_id=?",
                (owner_id,),
            )
            tx.connection.execute(
                "UPDATE github_installations SET status='removed' WHERE owner_id=?",
                (owner_id,),
            )

    def disconnect(self, owner_id: str):
        with self.db.write() as tx:
            tx.connection.execute(
                "DELETE FROM github_connections WHERE owner_id=?", (owner_id,)
            )
            tx.connection.execute(
                "DELETE FROM github_oauth_flows WHERE owner_id=?", (owner_id,)
            )

    def webhook(
        self,
        delivery_id: UUID,
        event: str,
        action: str,
        installation_id: int | None,
        github_id: int | None,
    ) -> bool:
        with self.db.write() as tx:
            added = tx.connection.execute(
                "INSERT INTO github_webhook_deliveries VALUES (?) ON CONFLICT DO NOTHING",
                (str(delivery_id),),
            ).rowcount
            if not added:
                return False
            if event == "installation" and action in ("deleted", "suspend"):
                tx.connection.execute(
                    "UPDATE github_installations SET status=? WHERE installation_id=?",
                    (
                        "removed" if action == "deleted" else "suspended",
                        installation_id,
                    ),
                )
                tx.connection.execute(
                    "UPDATE github_connections SET status='pending' WHERE status='connected' AND NOT EXISTS (SELECT 1 FROM github_installations i WHERE i.owner_id=github_connections.owner_id AND i.status='active')"
                )
            if event == "github_app_authorization" and action == "revoked":
                tx.connection.execute(
                    "UPDATE github_installations SET status='removed' WHERE owner_id IN (SELECT owner_id FROM github_connections WHERE github_user_id=?)",
                    (github_id,),
                )
                tx.connection.execute(
                    "UPDATE github_connections SET status='revoked',token_ciphertext=NULL WHERE github_user_id=?",
                    (github_id,),
                )
        return True


def github_connection_router(
    settings: RuntimeSettings,
    auth: SupabaseAuth,
    sessions: LocalSessions | None,
    store: SQLiteGitHubConnections | None,
    github: GitHubClient,
) -> APIRouter:
    router = APIRouter()
    cipher = Fernet(settings.web_cookie_key) if settings.web_cookie_key else None

    async def barrier():
        if isinstance(store, SQLiteGitHubConnections):
            await store.ensure_durable()

    def seal(value):
        assert cipher is not None
        return cipher.encrypt(json.dumps(value).encode()).decode()

    def open_flow(value):
        if cipher is None:
            return None
        try:
            return json.loads(cipher.decrypt(value.encode(), ttl=FLOW_SECONDS))
        except (InvalidToken, ValueError, TypeError):
            return None

    async def owner(request: Request, response: Response) -> dict[str, str | None]:
        response.headers["Cache-Control"] = "no-store"
        if store is None or not all(
            (
                settings.github_app_client_id,
                settings.github_app_client_secret,
                settings.github_webhook_secret,
                settings.web_origin,
            )
        ):
            raise HTTPException(
                status_code=503,
                detail="GitHub connection unavailable",
                headers=NO_STORE,
            )
        return await authenticated_web_user(
            auth, sessions, request.cookies.get(SESSION_COOKIE, ""), response
        )

    @router.get("/auth/github/start")
    async def start(request: Request) -> RedirectResponse:
        session_response = Response()
        user = await owner(request, session_response)
        state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
        assert store is not None
        try:
            await asyncio.to_thread(store.begin, user["id"], user["session_id"], state)
        except (SQLAlchemyError, sqlite3.Error):
            raise HTTPException(
                status_code=503,
                detail="GitHub connection unavailable",
                headers=NO_STORE,
            ) from None
        await barrier()
        flow = seal(
            {
                "state": state,
                "verifier": verifier,
                "owner": user["id"],
                "session": user["session_id"],
            }
        )
        redirect = RedirectResponse(
            github.authorize_url(state, verifier), status_code=303, headers=NO_STORE
        )
        if session_response.headers.get("set-cookie"):
            redirect.headers.append(
                "set-cookie", session_response.headers["set-cookie"]
            )
        redirect.set_cookie(
            FLOW_COOKIE,
            flow,
            max_age=FLOW_SECONDS,
            httponly=True,
            secure=settings.web_cookie_secure,
            samesite="lax",
            path="/auth/github",
        )
        return redirect

    @router.get("/auth/github/callback")
    async def callback(request: Request) -> RedirectResponse:
        session_response = Response()
        user = await owner(request, session_response)
        flow = open_flow(request.cookies.get(FLOW_COOKIE, ""))
        state = request.query_params.get("state", "")
        if (
            not flow
            or not state
            or not secrets.compare_digest(state, str(flow.get("state", "")))
            or flow.get("owner") != user["id"]
            or flow.get("session") != user["session_id"]
        ):
            raise HTTPException(
                status_code=400, detail="invalid GitHub callback", headers=NO_STORE
            )
        assert store is not None
        try:
            consumed = await asyncio.to_thread(
                store.consume, user["id"], user["session_id"], state
            )
        except (SQLAlchemyError, sqlite3.Error):
            raise HTTPException(
                status_code=503,
                detail="GitHub connection unavailable",
                headers=NO_STORE,
            ) from None
        await barrier()
        if not consumed:
            raise HTTPException(
                status_code=400, detail="invalid GitHub callback", headers=NO_STORE
            )
        if request.query_params.get("error"):
            redirect = RedirectResponse(
                "/?github=cancelled", status_code=303, headers=NO_STORE
            )
        else:
            code = request.query_params.get("code", "")
            if not code or len(code) > 2048:
                raise HTTPException(
                    status_code=400, detail="invalid GitHub callback", headers=NO_STORE
                )
            try:
                token = await github.exchange(code, flow["verifier"])
                (
                    github_id,
                    login,
                    installations,
                ) = await github.identity_and_installations(token)
                await asyncio.to_thread(
                    store.connect, user["id"], github_id, login, token, installations
                )
            except (GitHubUnauthorized, GitHubPending):
                raise HTTPException(
                    status_code=400,
                    detail="GitHub authorization denied",
                    headers=NO_STORE,
                ) from None
            except GitHubUnavailable:
                raise HTTPException(
                    status_code=503, detail="GitHub unavailable", headers=NO_STORE
                ) from None
            except (IntegrityError, sqlite3.IntegrityError):
                raise HTTPException(
                    status_code=409,
                    detail="GitHub account already linked",
                    headers=NO_STORE,
                ) from None
            except (SQLAlchemyError, sqlite3.Error):
                raise HTTPException(
                    status_code=503,
                    detail="GitHub connection unavailable",
                    headers=NO_STORE,
                ) from None
            await barrier()
            redirect = RedirectResponse(
                "/?github=connected", status_code=303, headers=NO_STORE
            )
        if session_response.headers.get("set-cookie"):
            redirect.headers.append(
                "set-cookie", session_response.headers["set-cookie"]
            )
        redirect.delete_cookie(FLOW_COOKIE, path="/auth/github")
        return redirect

    @router.get("/auth/github")
    async def status(request: Request, response: Response) -> dict[str, Any]:
        user = await owner(request, response)
        assert store is not None
        try:
            await barrier()
            current = await asyncio.to_thread(store.current, user["id"])
            if current is None:
                return {"status": "disconnected", "login": None, "installations": []}
            github_id, login, token, connection_status = current
            if connection_status == "revoked" or token is None:
                return {"status": "revoked", "login": login, "installations": []}
            try:
                verified_id, _, installations = await github.identity_and_installations(
                    token
                )
            except (GitHubUnauthorized, GitHubPending):
                await asyncio.to_thread(store.mark_revoked, user["id"])
                await barrier()
                return {"status": "revoked", "login": login, "installations": []}
            if verified_id != github_id:
                await asyncio.to_thread(store.mark_revoked, user["id"])
                await barrier()
                return {"status": "revoked", "login": login, "installations": []}
            result = await asyncio.to_thread(
                store.refresh, user["id"], github_id, installations
            )
            await barrier()
            return result
        except GitHubUnavailable:
            raise HTTPException(
                status_code=503, detail="GitHub unavailable", headers=NO_STORE
            ) from None
        except (SQLAlchemyError, sqlite3.Error):
            raise HTTPException(
                status_code=503,
                detail="GitHub connection unavailable",
                headers=NO_STORE,
            ) from None

    @router.delete("/auth/github")
    async def disconnect(request: Request, response: Response) -> dict[str, Any]:
        _require_origin(request, settings)
        user = await owner(request, response)
        assert store is not None
        try:
            await asyncio.to_thread(store.disconnect, user["id"])
        except (SQLAlchemyError, sqlite3.Error):
            raise HTTPException(
                status_code=503,
                detail="GitHub connection unavailable",
                headers=NO_STORE,
            ) from None
        await barrier()
        return {"status": "disconnected", "login": None, "installations": []}

    @router.post("/webhooks/github")
    async def webhook(request: Request) -> dict[str, bool]:
        if store is None or not settings.github_webhook_secret:
            raise HTTPException(status_code=503, detail="webhook unavailable")
        body = await request.body()
        if len(body) > 1024 * 1024:
            raise HTTPException(status_code=413, detail="webhook too large")
        signature = request.headers.get("X-Hub-Signature-256", "")
        expected = (
            "sha256="
            + hmac.new(
                settings.github_webhook_secret.encode(), body, hashlib.sha256
            ).hexdigest()
        )
        if not hmac.compare_digest(signature, expected):
            raise HTTPException(status_code=401, detail="invalid webhook signature")
        try:
            delivery = UUID(request.headers.get("X-GitHub-Delivery", ""))
            payload = json.loads(body)
            if not isinstance(payload, dict):
                raise ValueError
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="invalid webhook") from None
        event, action = (
            request.headers.get("X-GitHub-Event", ""),
            payload.get("action", ""),
        )
        installation = payload.get("installation")
        sender = payload.get("sender")
        installation_id = (
            installation.get("id") if isinstance(installation, dict) else None
        )
        github_id = sender.get("id") if isinstance(sender, dict) else None
        if type(installation_id) is not int or installation_id <= 0:
            installation_id = None
        if type(github_id) is not int or github_id <= 0:
            github_id = None
        if (
            event == "installation"
            and action in ("deleted", "suspend")
            and installation_id is None
        ):
            raise HTTPException(status_code=400, detail="invalid webhook")
        if (
            event == "github_app_authorization"
            and action == "revoked"
            and github_id is None
        ):
            raise HTTPException(status_code=400, detail="invalid webhook")
        try:
            applied = await asyncio.to_thread(
                store.webhook, delivery, event, action, installation_id, github_id
            )
        except (SQLAlchemyError, sqlite3.Error):
            raise HTTPException(status_code=503, detail="webhook unavailable") from None
        await barrier()
        return {"applied": applied}

    return router
