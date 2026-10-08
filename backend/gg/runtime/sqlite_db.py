"""Local runtime SQLite: explicit creation, leased lifecycle, revisioned writes."""

from __future__ import annotations

import fcntl
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from gg.runtime.sqlite_migrations import apply_migrations, validate_schema


@contextmanager
def database_lease(path: Path, *, exclusive: bool = False) -> Iterator[None]:
    """Cooperating local processes only; not a distributed Volume lock."""
    with Path(f"{path.resolve()}.lock").open("a+b") as lock:
        try:
            fcntl.flock(
                lock, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB
            )
        except BlockingIOError as exc:
            raise RuntimeError("database is in use; stop the runtime first") from exc
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def connect(path: Path) -> sqlite3.Connection:
    """Open existing state only. All writable connections use the same PRAGMAs."""
    connection = sqlite3.connect(
        path.resolve().as_uri() + "?mode=rw", uri=True, isolation_level=None
    )
    try:
        connection.execute("PRAGMA busy_timeout = 10000")
        if connection.execute("PRAGMA journal_mode = WAL").fetchone()[0] != "wal":
            raise RuntimeError("WAL unavailable")
        connection.execute("PRAGMA synchronous = FULL")
        connection.execute("PRAGMA foreign_keys = ON")
        return connection
    except BaseException:
        connection.close()
        raise


def initialize(path: Path) -> None:
    """Explicit init refuses any existing file, including invalid/empty state."""
    path = path.resolve()
    with database_lease(path, exclusive=True):
        if any(
            Path(f"{path}{suffix}").exists() for suffix in ("-wal", "-shm", "-journal")
        ):
            raise FileExistsError("database sidecars already exist")
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        try:
            connection = connect(path)
            try:
                apply_migrations(connection)
                # A newly created, unobserved database starts at revision zero.
                # Upgrading existing state still advances revisions per migration.
                connection.execute("UPDATE runtime_metadata SET revision = 0")
            finally:
                connection.close()
        except BaseException:
            path.unlink(missing_ok=True)
            for suffix in ("-wal", "-shm"):
                Path(f"{path}{suffix}").unlink(missing_ok=True)
            raise


@dataclass
class WriteTransaction:
    connection: sqlite3.Connection
    revision: int | None = None  # Assigned only after successful commit.


def _authorize_write(
    action: int, table: str | None, column: str | None, *_: object
) -> int:
    if action in (
        sqlite3.SQLITE_TRANSACTION,
        sqlite3.SQLITE_SAVEPOINT,
        sqlite3.SQLITE_ATTACH,
        sqlite3.SQLITE_DETACH,
        sqlite3.SQLITE_PRAGMA,
    ):
        return sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_ALTER_TABLE and column == "runtime_metadata":
        return sqlite3.SQLITE_DENY
    if table == "runtime_metadata" and action != sqlite3.SQLITE_READ:
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


class SQLiteDB:
    """Hold a shared lifecycle lease until close; one connection per operation."""

    def __init__(self, path: Path):
        self.path = path.resolve()
        if not self.path.is_file():
            raise FileNotFoundError(self.path)
        self._lease = database_lease(self.path)
        self._lease.__enter__()
        self._closed = False
        try:
            with self.read() as connection:
                validate_schema(connection)
        except BaseException:
            self.close()
            raise

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        if self._closed:
            raise RuntimeError("database closed")
        connection = connect(self.path)
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        with self._connection() as connection:
            connection.execute("PRAGMA query_only = ON")
            connection.execute("BEGIN")
            try:
                yield connection
            finally:
                connection.rollback()

    @contextmanager
    def write(self) -> Iterator[WriteTransaction]:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            transaction = WriteTransaction(connection)
            try:
                connection.set_authorizer(_authorize_write)
                yield transaction
                connection.set_authorizer(None)
                revision = connection.execute(
                    "UPDATE runtime_metadata SET revision = revision + 1 "
                    "RETURNING revision"
                ).fetchone()[0]
                connection.commit()
                transaction.revision = revision
            except BaseException:
                connection.set_authorizer(None)
                connection.rollback()
                raise

    @property
    def revision(self) -> int:
        with self.read() as connection:
            return validate_schema(connection)

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._lease.__exit__(None, None, None)

    def __enter__(self) -> SQLiteDB:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
