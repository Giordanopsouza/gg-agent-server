"""Isolated local Postgres ledger for tests that exercise durable task state."""

from __future__ import annotations

import os
from dataclasses import replace
from urllib.parse import urlsplit

import psycopg
import pytest
from psycopg import sql

from gg.runtime.ledger import TaskLedger
from gg.runtime.postgres import RuntimePostgres


_active: RuntimePostgres | None = None
_TABLES = (
    "sandbox_creations",
    "task_reservations",
    "publication_intents",
    "task_supervisions",
    "task_event_copies",
    "task_message_receipts",
    "task_results",
    "retention_tombstones",
)


def new_ledger() -> TaskLedger:
    global _active
    url = os.getenv("GG_RUNTIME_DATABASE_URL", "")
    if urlsplit(url).hostname not in {"127.0.0.1", "localhost"}:
        pytest.skip("requires a local runtime Postgres URL")
    database = replace(
        RuntimePostgres.from_env(),
        schema=os.getenv("GG_RUNTIME_TEST_SCHEMA", "runtime_private"),
    )
    if _active is None:
        with psycopg.connect(database.url, **database.connection_kwargs()) as conn:
            count = conn.execute(
                sql.SQL("SELECT count(*) FROM {}.tasks").format(
                    sql.Identifier(database.schema)
                )
            ).fetchone()
            if count and count[0]:
                pytest.skip("requires an empty local runtime tasks table")
        _active = database
    return TaskLedger(database)


def clean_test_ledger() -> None:
    global _active
    database = _active
    _active = None
    if database is None:
        return
    with psycopg.connect(database.url, **database.connection_kwargs()) as conn:
        for table in _TABLES:
            conn.execute(
                sql.SQL("DELETE FROM {}.{}").format(
                    sql.Identifier(database.schema), sql.Identifier(table)
                )
            )
        conn.execute(
            sql.SQL("DELETE FROM {}.tasks").format(sql.Identifier(database.schema))
        )
