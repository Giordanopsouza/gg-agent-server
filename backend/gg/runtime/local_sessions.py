"""Local Google identities and opaque, seven-day sessions in the runtime DB."""

from __future__ import annotations

import hashlib
import secrets
import time
from uuid import uuid4

from fastapi import HTTPException

from gg.runtime.checkpoints import CheckpointCoordinator
from gg.runtime.sqlite_db import SQLiteDB


SESSION_SECONDS = 7 * 24 * 60 * 60


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def durable(checkpoints: CheckpointCoordinator, revision: int) -> None:
    try:
        await checkpoints.ensure_durable(revision)
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="state persistence unavailable",
            headers={"Cache-Control": "no-store", "Retry-After": "1"},
        ) from None


class LocalSessions:
    def __init__(self, db: SQLiteDB, checkpoints: CheckpointCoordinator):
        if checkpoints.db is not db:
            raise ValueError("sessions and checkpoints must share a database")
        self.db = db
        self.checkpoints = checkpoints
        self.startup_revision = db.revision

    def insert(self, connection, sub: str, email: str, token: str) -> str:
        """Join profile/session creation to a caller's write transaction."""
        if not sub or not email:
            raise ValueError("Google identity is required")
        owner = connection.execute(
            "INSERT INTO local_users VALUES (?, ?, ?) ON CONFLICT(google_sub) "
            "DO UPDATE SET email = excluded.email RETURNING id",
            (str(uuid4()), sub, email),
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO local_sessions(token_hash, owner_id, expires_at) VALUES "
            "(?, ?, ?)",
            (token_hash(token), owner, int(time.time()) + SESSION_SECONDS),
        )
        return owner

    async def create(self, sub: str, email: str) -> str:
        token = secrets.token_urlsafe(32)
        with self.db.write() as tx:
            self.insert(tx.connection, sub, email, token)
        await durable(self.checkpoints, tx.revision)
        return token

    async def user(self, token: str) -> dict[str, str]:
        await durable(self.checkpoints, self.db.revision)
        with self.db.read() as connection:
            row = connection.execute(
                "SELECT u.id, u.email FROM local_sessions s JOIN local_users u "
                "ON u.id = s.owner_id WHERE token_hash = ? AND revoked = 0 "
                "AND expires_at > ?",
                (token_hash(token), int(time.time())),
            ).fetchone()
        if row is None:
            raise HTTPException(status_code=401, detail="session expired or absent")
        return {"id": row[0], "email": row[1]}

    async def revoke(self, token: str) -> None:
        with self.db.write() as tx:
            tx.connection.execute(
                "UPDATE local_sessions SET revoked = 1 WHERE token_hash = ?",
                (token_hash(token),),
            )
        await durable(self.checkpoints, tx.revision)
