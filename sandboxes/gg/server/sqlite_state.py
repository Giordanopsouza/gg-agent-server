"""Sandbox-local SQLite state, shared by the server and standalone Pi helper."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from gg.server.observability import trace_sqlite_query


class ObservedConnection(sqlite3.Connection):
    """Trace the Connection.execute calls used throughout the sandbox."""

    def execute(self, sql, parameters=(), /):
        return trace_sqlite_query(
            sql, lambda: sqlite3.Connection.execute(self, sql, parameters)
        )


SCHEMA = (
    """CREATE TABLE conversations (directory TEXT PRIMARY KEY NOT NULL,
       meta_json TEXT CHECK(json_valid(meta_json)),
       base_json TEXT CHECK(json_valid(base_json))) STRICT""",
    """CREATE TABLE events (conversation TEXT NOT NULL
       REFERENCES conversations(directory),
       seq INTEGER NOT NULL CHECK(seq > 0), id TEXT NOT NULL,
       payload TEXT NOT NULL CHECK(json_valid(payload)),
       PRIMARY KEY(conversation, seq), UNIQUE(conversation, id)) STRICT""",
    """CREATE TABLE message_receipts (conversation TEXT NOT NULL
       REFERENCES conversations(directory),
       message_id TEXT NOT NULL, payload TEXT NOT NULL CHECK(json_valid(payload)),
       PRIMARY KEY(conversation, message_id)) STRICT""",
    """CREATE TABLE executions (execution_id TEXT PRIMARY KEY NOT NULL,
       start_key TEXT UNIQUE NOT NULL, phase TEXT NOT NULL,
       payload TEXT NOT NULL CHECK(json_valid(payload))) STRICT""",
    "CREATE INDEX executions_phase ON executions(phase, execution_id)",
    """CREATE TABLE manifests (execution_id TEXT PRIMARY KEY NOT NULL
       REFERENCES executions(execution_id),
       payload TEXT NOT NULL CHECK(json_valid(payload))) STRICT""",
    """CREATE TABLE publication_intents (task_marker TEXT PRIMARY KEY NOT NULL,
       payload TEXT NOT NULL CHECK(json_valid(payload))) STRICT""",
)


def conversation_database(conversation_dir: Path | str) -> Path:
    return Path(conversation_dir).parent / "sandbox.db"


class SandboxState:
    """One configured connection per operation, with short atomic transactions."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.write() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                for statement in SCHEMA:
                    connection.execute(statement)
                connection.execute("PRAGMA user_version = 1")
                version = 1
            if version == 1:
                connection.execute(
                    """CREATE TABLE sandbox_metadata (name TEXT PRIMARY KEY NOT NULL,
                       value TEXT NOT NULL) STRICT"""
                )
                connection.execute("PRAGMA user_version = 2")
            elif version != 2:
                raise RuntimeError(f"unsupported sandbox schema version {version}")

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(
            self.path,
            timeout=10,
            isolation_level=None,
            factory=ObservedConnection,
        )
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA busy_timeout = 10000")
            connection.execute("PRAGMA foreign_keys = ON")
            if (
                connection.execute("PRAGMA journal_mode = DELETE").fetchone()[0]
                != "delete"
            ):
                raise RuntimeError("sandbox state requires DELETE journal")
            connection.execute("PRAGMA synchronous = FULL")
            yield connection
        finally:
            connection.close()

    @contextmanager
    def write(self) -> Iterator[sqlite3.Connection]:
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
