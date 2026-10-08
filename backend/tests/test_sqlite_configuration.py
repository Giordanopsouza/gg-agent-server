"""Runtime startup accepts only an explicitly initialized SQLite database."""

import sqlite3

import pytest

from gg.runtime.app import create_app
from gg.runtime.config import RuntimeSettings
from gg.runtime.sqlite_db import SQLiteDB, initialize
from gg.runtime.sqlite_migrations import SCHEMA_VERSION, InvalidDatabase


def test_runtime_requires_explicit_database_and_snapshot_paths(monkeypatch):
    monkeypatch.delenv("GG_RUNTIME_DB_PATH", raising=False)
    monkeypatch.delenv("GG_RUNTIME_SNAPSHOT_PATH", raising=False)
    with pytest.raises(RuntimeError, match="GG_RUNTIME_DB_PATH"):
        create_app(RuntimeSettings(api_key="control-secret"))


def test_missing_and_future_database_fail_closed(tmp_path):
    path = tmp_path / "runtime.db"
    with pytest.raises(FileNotFoundError):
        SQLiteDB(path)
    assert not path.exists()

    initialize(path)
    with sqlite3.connect(path, isolation_level=None) as connection:
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    with pytest.raises(InvalidDatabase, match="version"):
        SQLiteDB(path)
