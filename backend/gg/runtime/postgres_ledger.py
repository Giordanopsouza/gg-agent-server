"""Postgres implementation of the durable task ledger contract.

The existing ledger methods issue short explicit transactions. Every writer
acquires one transaction-scoped advisory lock, so sequence assignment,
capacity checks and publication decisions serialize across runtime processes.
The lock is released by commit or rollback, including on process death.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from gg.runtime.ledger import TaskLedger
from gg.runtime.postgres import RuntimePostgres


class _ChangesCursor:
    def __init__(self, count: int) -> None:
        self._count = count

    def fetchone(self) -> tuple[int]:
        return (self._count,)


class _LedgerConnection:
    """Translate the ledger's parameter syntax, not its SQL semantics."""

    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self.connection = connection
        self.last_changes = 0

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> Any:
        statement = sql.strip()
        if statement == "BEGIN IMMEDIATE":
            self.connection.execute("BEGIN")
            # One namespace-specific key. The transaction lock also protects
            # MAX(seq)+1 and the global capacity count from concurrent writers.
            self.connection.execute("SELECT pg_advisory_xact_lock(780078)")
            return None
        if statement == "SELECT changes()":
            return _ChangesCursor(self.last_changes)
        cursor = self.connection.execute(sql.replace("?", "%s"), params)
        self.last_changes = cursor.rowcount
        return cursor

    def close(self) -> None:
        self.connection.close()


class PostgresTaskLedger(TaskLedger):
    """Runtime ledger stored solely in ``runtime_private`` Postgres tables."""

    def __init__(self, database: RuntimePostgres) -> None:
        self._database = database
        self._lock = threading.Lock()
        self._conn: _LedgerConnection | None = None
        self._db_path = "postgres"
        self._expected_schema_version = 7

    def _owner_param(self, owner_id: UUID | None) -> UUID | None:
        return owner_id

    def open(self) -> None:
        if self._conn is not None:
            return
        config = self._database.connection_kwargs()
        connection = psycopg.connect(
            self._database.url, autocommit=True, row_factory=dict_row, **config
        )
        try:
            connection.execute("SET search_path TO runtime_private")
            self._conn = _LedgerConnection(connection)
            version = self._schema_version()
            if version != self._expected_schema_version:
                raise RuntimeError(
                    f"unsupported Postgres ledger schema version {version}; "
                    f"expected {self._expected_schema_version}"
                )
        except Exception:
            connection.close()
            self._conn = None
            raise

    def ping_database(self) -> bool:
        try:
            assert self._conn is not None
            with self._lock:
                self._conn.execute("SELECT 1")
        except (psycopg.Error, AssertionError):
            return False
        return True

    def online_backup(self, destination: Path | str) -> None:
        raise RuntimeError("Use a logical Postgres export and restore rehearsal")


__all__ = ["PostgresTaskLedger"]
