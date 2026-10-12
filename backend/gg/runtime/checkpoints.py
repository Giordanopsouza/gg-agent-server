"""Closed, validated snapshots and serialized revision durability barriers."""

from __future__ import annotations

import asyncio
import os
import sqlite3
import tempfile
from collections.abc import Awaitable, Callable
from pathlib import Path

from gg.runtime.sqlite_db import ObservedConnection, SQLiteDB
from gg.runtime.sqlite_migrations import (
    SCHEMA_VERSION,
    InvalidDatabase,
    validate_schema,
)


def validate_snapshot(path: Path, *, allow_older: bool = False) -> int:
    """Read without changing the source or consuming any WAL sidecar."""
    if not path.is_file():
        raise FileNotFoundError(path)
    if any(Path(f"{path}{suffix}").exists() for suffix in ("-wal", "-shm", "-journal")):
        raise InvalidDatabase("snapshot must be self-contained; sidecars found")
    with path.open("rb") as snapshot:
        header = snapshot.read(100)
    if header[:16] != b"SQLite format 3\x00" or header[18:20] != b"\x01\x01":
        raise InvalidDatabase("snapshot has invalid or WAL-dependent header")
    connection = sqlite3.connect(
        path.resolve().as_uri() + "?mode=ro&immutable=1",
        uri=True,
        factory=ObservedConnection,
    )
    try:
        if connection.execute("PRAGMA journal_mode").fetchone()[0] != "delete":
            raise InvalidDatabase("snapshot must use DELETE journal mode")
        if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise InvalidDatabase("snapshot integrity check failed")
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise InvalidDatabase("snapshot has broken foreign keys")
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if allow_older and 1 <= version <= SCHEMA_VERSION:
            return validate_schema(connection, version=version)
        return validate_schema(connection)
    except sqlite3.DatabaseError as exc:
        raise InvalidDatabase("corrupt snapshot") from exc
    finally:
        connection.close()


def publish_snapshot(db: SQLiteDB, destination: Path) -> int:
    """backup() includes WAL commits; revision is read from the completed copy."""
    with db.read() as source:
        return publish_connection_snapshot(source, destination)


def publish_connection_snapshot(source: sqlite3.Connection, destination: Path) -> int:
    """Administrative backup under an exclusive lifecycle lease."""
    active = Path(source.execute("PRAGMA database_list").fetchone()[2]).resolve()
    destination = destination.resolve()
    reserved = {
        active,
        *(Path(f"{active}{s}") for s in ("-wal", "-shm", "-journal", ".lock")),
    }
    if destination in reserved or (
        destination.exists() and destination.samefile(active)
    ):
        raise ValueError("snapshot destination must differ from active database")
    if any(
        Path(f"{destination}{suffix}").exists()
        for suffix in ("-wal", "-shm", "-journal")
    ):
        raise InvalidDatabase("snapshot destination has sidecars")
    descriptor, filename = tempfile.mkstemp(
        prefix=f".{destination.name}-", dir=destination.parent
    )
    os.close(descriptor)
    temporary = Path(filename)
    try:
        target = sqlite3.connect(
            temporary, isolation_level=None, factory=ObservedConnection
        )
        try:
            source.backup(target)
            target.execute("PRAGMA journal_mode = DELETE")
        finally:
            target.close()
        revision = validate_snapshot(temporary)
        with temporary.open("rb") as snapshot:
            os.fsync(snapshot.fileno())
        os.replace(temporary, destination)
        directory = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        return revision
    finally:
        temporary.unlink(missing_ok=True)
        for suffix in ("-wal", "-shm", "-journal"):
            Path(f"{temporary}{suffix}").unlink(missing_ok=True)


class CheckpointCoordinator:
    """One coordinator per runtime/Volume; commit can be Volume.commit.aio.

    A published local snapshot is not confirmed until commit returns. Callers
    awaiting a failed checkpoint must treat their already committed local write
    as pending, not rolled back. Background scheduling is supplied by the runtime.
    """

    def __init__(
        self, db: SQLiteDB, snapshot: Path, commit: Callable[[], Awaitable[None]]
    ):
        self.db = db
        self.snapshot = snapshot
        self.commit = commit
        self.confirmed_revision = -1
        self.last_error: str | None = None
        self._lock = asyncio.Lock()
        self._confirmed = asyncio.Condition()

    @property
    def pending(self) -> bool:
        return self.db.revision > self.confirmed_revision

    async def run(self):
        """Background activity checkpoint; failures suspend new effects until retry."""
        while True:
            await asyncio.sleep(2)
            if self.pending or self.last_error:
                try:
                    await self.checkpoint()
                except Exception:
                    pass  # checkpoint records only a sanitized failure category.

    async def checkpoint(self, *, required_revision: int | None = None) -> int:
        try:
            return await self._checkpoint(required_revision)
        except BaseException as exc:
            self.last_error = type(exc).__name__
            raise

    async def _checkpoint(self, required_revision: int | None) -> int:
        async with self._lock:
            # Explicit checkpoints always publish; revision waiters coalesce.
            if (
                required_revision is not None
                and self.confirmed_revision >= required_revision
            ):
                return self.confirmed_revision
            revision = publish_snapshot(self.db, self.snapshot)
            commit = asyncio.create_task(self.commit())
            try:
                await asyncio.shield(commit)
            except asyncio.CancelledError:
                # Keep the serialization lock until the in-flight commit settles.
                # Its outcome remains unconfirmed; a retry will publish again.
                while not commit.done():
                    try:
                        await asyncio.shield(commit)
                    except asyncio.CancelledError:
                        continue
                    except Exception:
                        break
                if not commit.cancelled():
                    # Retrieve a possible failure without confirming.
                    commit.exception()
                raise
            async with self._confirmed:
                self.confirmed_revision = revision
                self.last_error = None
                self._confirmed.notify_all()
            return revision

    async def ensure_durable(self, revision: int) -> None:
        if revision < 0 or revision > self.db.revision:
            raise ValueError("revision must name a committed local write")
        while self.confirmed_revision < revision:
            await self.checkpoint(required_revision=revision)

    async def wait_until_confirmed(self, revision: int) -> None:
        """Passive waiter; failures/cancellation do not release it as successful."""
        if revision < 0 or revision > self.db.revision:
            raise ValueError("revision must name a committed local write")
        async with self._confirmed:
            await self._confirmed.wait_for(lambda: self.confirmed_revision >= revision)
