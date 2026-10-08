"""Private per-user OpenRouter credentials; only masked metadata crosses HTTP."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from typing import TYPE_CHECKING, Any
from uuid import UUID

import httpx
import psycopg
from cryptography.fernet import Fernet
from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from gg.runtime.checkpoints import CheckpointCoordinator
from gg.runtime.config import RuntimeSettings
from gg.runtime.local_sessions import LocalSessions, durable
from gg.runtime.sqlite_db import SQLiteDB
from gg.runtime.web_auth import (
    SESSION_COOKIE,
    SupabaseAuth,
    _require_origin,
    authenticated_web_user,
)


if TYPE_CHECKING:
    from gg.runtime.google_auth import GoogleAuth


OPENROUTER_KEY_URL = "https://openrouter.ai/api/v1/key"
NO_STORE = {"Cache-Control": "no-store"}


class PostgresOpenRouterVault:
    def __init__(self, engine: Engine, encryption_key: str) -> None:
        self.engine = engine
        self.cipher = Fernet(encryption_key)

    def status(self, owner_id: str) -> dict[str, Any]:
        with self.engine.begin() as connection:
            connection.exec_driver_sql(
                "select set_config('app.user_id', %s, true)", (owner_id,)
            )
            row = connection.exec_driver_sql(
                "select mask, credential_version "
                "from vault_private.openrouter_credentials where owner_id = %s",
                (UUID(owner_id),),
            ).fetchone()
            return (
                {"configured": row[0] is not None, "mask": row[0], "version": row[1]}
                if row
                else {"configured": False, "mask": None, "version": None}
            )

    def resolve(self, owner_id: str) -> tuple[str, int] | None:
        """Read only the current owner's key at dispatch; never put it in a queue."""
        with self.engine.begin() as connection:
            connection.exec_driver_sql(
                "select set_config('app.user_id', %s, true)", (owner_id,)
            )
            row = connection.exec_driver_sql(
                "select ciphertext, credential_version from "
                "vault_private.openrouter_credentials "
                "where owner_id = %s and ciphertext is not null",
                (UUID(owner_id),),
            ).fetchone()
        if row is None:
            return None
        return self.cipher.decrypt(row[0]).decode(), row[1]

    def replace(self, owner_id: str, api_key: str) -> dict[str, Any]:
        ciphertext = self.cipher.encrypt(api_key.encode())
        mask = f"••••{api_key[-4:]}"
        with self.engine.begin() as connection:
            connection.exec_driver_sql(
                "select set_config('app.user_id', %s, true)", (owner_id,)
            )
            row = connection.exec_driver_sql(
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
        with self.engine.begin() as connection:
            connection.exec_driver_sql(
                "select set_config('app.user_id', %s, true)", (owner_id,)
            )
            row = connection.exec_driver_sql(
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


class SQLiteOpenRouterVault:
    """Candidate with the existing sync dispatch interface and HTTP barrier."""

    def __init__(
        self, db: SQLiteDB, encryption_key: str, checkpoints: CheckpointCoordinator
    ):
        if checkpoints.db is not db:
            raise ValueError("vault and checkpoints must share a database")
        self.db = db
        self.checkpoints = checkpoints
        self.cipher = Fernet(encryption_key)

    async def ensure_durable(self) -> None:
        await durable(self.checkpoints, self.db.revision)

    def status(self, owner_id: str) -> dict[str, Any]:
        with self.db.read() as connection:
            row = connection.execute(
                "SELECT mask, credential_version FROM openrouter_credentials WHERE "
                "owner_id = ?",
                (str(UUID(owner_id)),),
            ).fetchone()
        return (
            {"configured": row[0] is not None, "mask": row[0], "version": row[1]}
            if row
            else {"configured": False, "mask": None, "version": None}
        )

    def resolve(self, owner_id: str) -> tuple[str, int] | None:
        with self.db.read() as connection:
            row = connection.execute(
                "SELECT ciphertext, credential_version FROM openrouter_credentials "
                "WHERE owner_id = ? AND ciphertext IS NOT NULL",
                (str(UUID(owner_id)),),
            ).fetchone()
        return (self.cipher.decrypt(row[0]).decode(), row[1]) if row else None

    def replace(self, owner_id: str, api_key: str) -> dict[str, Any]:
        ciphertext, mask = self.cipher.encrypt(api_key.encode()), f"••••{api_key[-4:]}"
        with self.db.write() as tx:
            row = tx.connection.execute(
                "INSERT INTO openrouter_credentials VALUES (?, ?, ?, 1) ON "
                "CONFLICT(owner_id) "
                "DO UPDATE SET ciphertext = excluded.ciphertext, mask = excluded.mask, "
                "credential_version = credential_version + 1 RETURNING "
                "credential_version",
                (str(UUID(owner_id)), ciphertext, mask),
            ).fetchone()
        return {"configured": True, "mask": mask, "version": row[0]}

    def remove(self, owner_id: str) -> dict[str, Any]:
        with self.db.write() as tx:
            row = tx.connection.execute(
                "UPDATE openrouter_credentials SET ciphertext = NULL, mask = NULL, "
                "credential_version = credential_version + 1 WHERE owner_id = ? "
                "RETURNING credential_version",
                (str(UUID(owner_id)),),
            ).fetchone()
        return {"configured": False, "mask": None, "version": row[0] if row else None}


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
    auth: SupabaseAuth | GoogleAuth,
    sessions: LocalSessions | None,
    vault: PostgresOpenRouterVault | SQLiteOpenRouterVault | None,
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
            result = await asyncio.to_thread(vault.status, user_id)
            if isinstance(vault, SQLiteOpenRouterVault):
                await vault.ensure_durable()
            return result
        except (SQLAlchemyError, psycopg.Error, sqlite3.Error):
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
            result = await asyncio.to_thread(vault.replace, user_id, api_key)
            if isinstance(vault, SQLiteOpenRouterVault):
                await vault.ensure_durable()
            return result
        except (SQLAlchemyError, psycopg.Error, sqlite3.Error):
            raise HTTPException(
                status_code=503, detail="credential vault unavailable", headers=NO_STORE
            ) from None

    @router.delete("")
    async def remove(request: Request, response: Response) -> dict[str, Any]:
        _require_origin(request, settings)
        user_id = await owner(request, response)
        assert vault is not None
        try:
            result = await asyncio.to_thread(vault.remove, user_id)
            if isinstance(vault, SQLiteOpenRouterVault):
                await vault.ensure_durable()
            return result
        except (SQLAlchemyError, psycopg.Error, sqlite3.Error):
            raise HTTPException(
                status_code=503, detail="credential vault unavailable", headers=NO_STORE
            ) from None

    return router
