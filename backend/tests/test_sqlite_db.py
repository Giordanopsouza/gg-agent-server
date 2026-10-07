"""Transaction demo: independent connections, WAL, rollback, lock and restart."""

import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from gg.runtime.sqlite_db import SQLiteDB, connect, initialize
from gg.runtime.sqlite_migrations import (
    MIGRATIONS,
    InvalidDatabase,
    Migration,
    apply_migrations,
)


def test_pragmas_rollback_and_reopen(tmp_path):
    path = tmp_path / "runtime.db"
    initialize(path)
    with SQLiteDB(path) as db:
        with db.read() as connection:
            for pragma, expected in (
                ("journal_mode", "wal"),
                ("synchronous", 2),
                ("foreign_keys", 1),
                ("busy_timeout", 10000),
            ):
                assert connection.execute(f"PRAGMA {pragma}").fetchone()[0] == expected
        with db.write() as tx:
            tx.connection.execute(
                "CREATE TABLE demo (id INTEGER PRIMARY KEY, value TEXT)"
            )
        assert tx.revision == 1
        with pytest.raises(RuntimeError, match="interrupt"):
            with db.write() as failed:
                failed.connection.execute(
                    "INSERT INTO demo VALUES (?, ?)", (1, "rolled back")
                )
                raise RuntimeError("interrupt")
        assert failed.revision is None
        assert db.revision == 1
        with db.write() as tx:
            tx.connection.execute("INSERT INTO demo VALUES (?, ?)", (1, "quote'; --"))
        assert tx.revision == 2
    with SQLiteDB(path) as db, db.read() as connection:
        assert db.revision == 2
        assert (
            connection.execute("SELECT value FROM demo").fetchone()[0] == "quote'; --"
        )
        with pytest.raises(sqlite3.OperationalError):
            connection.execute("DELETE FROM demo")


def test_concurrent_writers_and_lock(tmp_path):
    path = tmp_path / "db"
    initialize(path)
    with SQLiteDB(path) as db:
        with db.write() as tx:
            tx.connection.execute("CREATE TABLE demo (id INTEGER PRIMARY KEY)")
        started, finished = Event(), Event()

        def write(value):
            with SQLiteDB(path) as other:
                started.set()
                with other.write() as tx:
                    tx.connection.execute("INSERT INTO demo VALUES (?)", (value,))
                finished.set()
                return tx.revision

        with ThreadPoolExecutor(max_workers=4) as pool:
            with db.write() as tx:
                tx.connection.execute("INSERT INTO demo VALUES (?)", (0,))
                future = pool.submit(write, 1)
                assert started.wait(2)
                assert not finished.wait(0.05)
            assert future.result(timeout=3) == 3
            revisions = list(pool.map(write, range(2, 22)))
        assert sorted(revisions) == list(range(4, 24))
        assert db.revision == 23
        with db.read() as connection:
            assert connection.execute("SELECT COUNT(*) FROM demo").fetchone()[0] == 22


@pytest.mark.parametrize(
    "statement",
    [
        "COMMIT",
        "PRAGMA user_version = 9",
        "UPDATE runtime_metadata SET revision = 99",
        "DROP TABLE runtime_metadata",
        "ALTER TABLE runtime_metadata RENAME TO other",
    ],
)
def test_store_cannot_bypass_revision(tmp_path, statement):
    path = tmp_path / "db"
    initialize(path)
    with SQLiteDB(path) as db:
        with pytest.raises(sqlite3.DatabaseError):
            with db.write() as tx:
                tx.connection.execute(statement)
        assert db.revision == 0


def test_migration_failure_is_atomic_and_retryable(tmp_path):
    path = tmp_path / "db"
    initialize(path)
    connection = connect(path)
    try:
        broken = MIGRATIONS + (
            Migration(2, ("CREATE TABLE demo (id INTEGER)", "INVALID SQL")),
        )
        with pytest.raises(sqlite3.OperationalError):
            apply_migrations(connection, broken)
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE name = 'demo'"
            ).fetchone()
            is None
        )
        assert (
            connection.execute("SELECT revision FROM runtime_metadata").fetchone()[0]
            == 0
        )
        fixed = MIGRATIONS + (Migration(2, ("CREATE TABLE demo (id INTEGER)",)),)
        apply_migrations(connection, fixed)
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        assert (
            connection.execute("SELECT revision FROM runtime_metadata").fetchone()[0]
            == 1
        )
        with pytest.raises(InvalidDatabase, match="future"):
            apply_migrations(connection)
        with pytest.raises(InvalidDatabase, match="sequential"):
            apply_migrations(connection, (Migration(3, ()),))
    finally:
        connection.close()
    with pytest.raises(InvalidDatabase, match="version"):
        SQLiteDB(path)


def test_missing_and_interrupted_database_fail_closed(tmp_path):
    path = tmp_path / "db"
    with pytest.raises(FileNotFoundError):
        SQLiteDB(path)
    assert not path.exists()
    connection = sqlite3.connect(path, isolation_level=None)
    connection.execute("CREATE TABLE partial (id INTEGER)")
    with pytest.raises(InvalidDatabase, match="interrupted"):
        apply_migrations(connection)
    connection.close()
    with pytest.raises(FileExistsError):
        initialize(path)


def test_foreign_keys_and_failed_write_do_not_advance_revision(tmp_path):
    path = tmp_path / "db"
    initialize(path)
    with SQLiteDB(path) as db:
        with db.write() as tx:
            tx.connection.execute("CREATE TABLE parent (id INTEGER PRIMARY KEY)")
            tx.connection.execute(
                "CREATE TABLE child (parent_id INTEGER REFERENCES parent(id))"
            )
        with pytest.raises(sqlite3.IntegrityError):
            with db.write() as tx:
                tx.connection.execute("INSERT INTO child VALUES (?)", (7,))
        assert db.revision == 1


def test_init_refuses_orphan_wal(tmp_path):
    path = tmp_path / "db"
    (tmp_path / "db-wal").write_bytes(b"orphan")
    with pytest.raises(FileExistsError, match="sidecars"):
        initialize(path)
    assert not path.exists()
    assert (tmp_path / "db-wal").read_bytes() == b"orphan"


def test_process_death_rolls_back_schema_and_version(tmp_path):
    path = tmp_path / "db"
    initialize(path)
    script = """
import os, sqlite3, sys
connection = sqlite3.connect(sys.argv[1], isolation_level=None)
connection.execute("BEGIN IMMEDIATE")
connection.execute("CREATE TABLE interrupted (id INTEGER)")
connection.execute("UPDATE runtime_metadata SET revision = revision + 1")
connection.execute("PRAGMA user_version = 2")
os._exit(17)
"""
    result = subprocess.run([sys.executable, "-c", script, str(path)], check=False)
    assert result.returncode == 17
    with SQLiteDB(path) as db, db.read() as connection:
        assert db.revision == 0
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE name = 'interrupted'"
            ).fetchone()
            is None
        )
