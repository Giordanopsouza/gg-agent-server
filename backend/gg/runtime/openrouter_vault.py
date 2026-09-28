"""Private per-user OpenRouter credentials; only masked metadata crosses HTTP."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import UUID

import httpx
import psycopg
from cryptography.fernet import Fernet
from fastapi import APIRouter, HTTPException, Request, Response
from psycopg_pool import ConnectionPool

from gg.runtime.config import RuntimeSettings
from gg.runtime.web_auth import (
    SESSION_COOKIE,
    PostgresWebSessions,
    SupabaseAuth,
    _require_origin,
    authenticated_web_user,
)


OPENROUTER_KEY_URL = "https://openrouter.ai/api/v1/key"
NO_STORE = {"Cache-Control": "no-store"}


class PostgresOpenRouterVault:
    def __init__(self, pool: ConnectionPool, encryption_key: str) -> None:
        self.pool = pool
        self.cipher = Fernet(encryption_key)

    def status(self, owner_id: str) -> dict[str, Any]:
        with self.pool.connection() as connection, connection.transaction():
            connection.execute(
                "select set_config('app.user_id', %s, true)", (owner_id,)
            )
            row = connection.execute(
                "select mask, credential_version "
                "from vault_private.openrouter_credentials where owner_id = %s",
                (UUID(owner_id),),
            ).fetchone()
            return (
                {"configured": row[0] is not None, "mask": row[0], "version": row[1]}
                if row
                else {"configured": False, "mask": None, "version": None}
            )

    def replace(self, owner_id: str, api_key: str) -> dict[str, Any]:
        ciphertext = self.cipher.encrypt(api_key.encode())
        mask = f"••••{api_key[-4:]}"
        with self.pool.connection() as connection, connection.transaction():
            connection.execute(
                "select set_config('app.user_id', %s, true)", (owner_id,)
            )
            row = connection.execute(
                "insert into vault_private.openrouter_credentials "
                "(owner_id, ciphertext, mask) values (%s, %s, %s) "
                "on conflict (owner_id) do update set "
                "ciphertext = excluded.ciphertext, mask = excluded.mask, "
                "credential_version = "
                "vault_private.openrouter_credentials.credential_version + 1, "
                "updated_at = now() returning credential_version",
                (UUID(owner_id), ciphertext, mask),
            ).fetchone()
            assert row is not None
            return {"configured": True, "mask": mask, "version": row[0]}

    def remove(self, owner_id: str) -> dict[str, Any]:
        with self.pool.connection() as connection, connection.transaction():
            connection.execute(
                "select set_config('app.user_id', %s, true)", (owner_id,)
            )
            row = connection.execute(
                "update vault_private.openrouter_credentials set "
                "ciphertext = null, mask = null, "
                "credential_version = credential_version + 1, "
                "updated_at = now() where owner_id = %s returning credential_version",
                (UUID(owner_id),),
            ).fetchone()
            return {
                "configured": False,
                "mask": None,
                "version": row[0] if row else None,
            }


class OpenRouterKeyVerifier:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.transport = transport

    async def verify(self, api_key: str) -> None:
        try:
            async with httpx.AsyncClient(
                transport=self.transport, timeout=10, follow_redirects=False
            ) as client:
                response = await client.get(
                    OPENROUTER_KEY_URL,
                    headers={"Authorization": f"Bearer {api_key}"},
                )
        except httpx.HTTPError:
            raise HTTPException(
                status_code=503, detail="OpenRouter unavailable", headers=NO_STORE
            ) from None
        if response.status_code == 200:
            return
        if response.status_code in (401, 403):
            raise HTTPException(
                status_code=400, detail="invalid OpenRouter key", headers=NO_STORE
            )
        if response.status_code in (402, 429):
            raise HTTPException(
                status_code=429, detail="OpenRouter limit reached", headers=NO_STORE
            )
        raise HTTPException(
            status_code=503, detail="OpenRouter unavailable", headers=NO_STORE
        )


def openrouter_vault_router(
    settings: RuntimeSettings,
    auth: SupabaseAuth,
    sessions: PostgresWebSessions | None,
    vault: PostgresOpenRouterVault | None,
    verifier: OpenRouterKeyVerifier,
) -> APIRouter:
    router = APIRouter(prefix="/auth/openrouter-credential")

    async def owner(request: Request, response: Response) -> str:
        response.headers["Cache-Control"] = "no-store"
        user = await authenticated_web_user(
            auth, sessions, request.cookies.get(SESSION_COOKIE, ""), response
        )
        if vault is None:
            raise HTTPException(
                status_code=503, detail="credential vault unavailable", headers=NO_STORE
            )
        return str(user["id"])

    @router.get("")
    async def status(request: Request, response: Response) -> dict[str, Any]:
        user_id = await owner(request, response)
        assert vault is not None
        try:
            return await asyncio.to_thread(vault.status, user_id)
        except psycopg.Error:
            raise HTTPException(
                status_code=503, detail="credential vault unavailable", headers=NO_STORE
            ) from None

    @router.put("")
    async def replace(request: Request, response: Response) -> dict[str, Any]:
        _require_origin(request, settings)
        user_id = await owner(request, response)
        if (
            request.headers.get("content-type", "").split(";", 1)[0]
            != "application/json"
        ):
            raise HTTPException(
                status_code=415, detail="JSON required", headers=NO_STORE
            )
        raw = await request.body()
        if len(raw) > 8192:
            raise HTTPException(
                status_code=413, detail="request too large", headers=NO_STORE
            )
        try:
            body = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            raise HTTPException(
                status_code=400, detail="invalid JSON", headers=NO_STORE
            ) from None
        api_key = body.get("api_key") if isinstance(body, dict) else None
        if (
            not isinstance(api_key, str)
            or not 8 <= len(api_key) <= 4096
            or api_key != api_key.strip()
            or any(ord(char) < 33 or ord(char) > 126 for char in api_key)
        ):
            raise HTTPException(
                status_code=400, detail="invalid key format", headers=NO_STORE
            )
        await verifier.verify(api_key)
        assert vault is not None
        try:
            return await asyncio.to_thread(vault.replace, user_id, api_key)
        except psycopg.Error:
            raise HTTPException(
                status_code=503, detail="credential vault unavailable", headers=NO_STORE
            ) from None

    @router.delete("")
    async def remove(request: Request, response: Response) -> dict[str, Any]:
        _require_origin(request, settings)
        user_id = await owner(request, response)
        assert vault is not None
        try:
            return await asyncio.to_thread(vault.remove, user_id)
        except psycopg.Error:
            raise HTTPException(
                status_code=503, detail="credential vault unavailable", headers=NO_STORE
            ) from None

    return router
