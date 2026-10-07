"""Local init -> WAL write -> backup -> restore -> data/revision comparison."""

import hashlib
import sqlite3
import subprocess
import sys

import pytest

from gg.runtime.checkpoints import validate_snapshot
from gg.runtime.db_cli import main, migrate, restore
from gg.runtime.sqlite_db import SQLiteDB, connect, initialize
from gg.runtime.sqlite_migrations import InvalidDatabase


def cli(command, db, snapshot):
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "gg.runtime.db_cli",
            command,
            "--db",
            str(db),
            "--snapshot",
            str(snapshot),
        ],
        text=True,
        capture_output=True,
        check=False,
    )


def test_real_cli_wal_backup_restore(tmp_path):
    path, snapshot = tmp_path / "db", tmp_path / "snapshot"
    result = cli("init", path, snapshot)
    assert result.returncode == 0, result.stderr
    assert "revision=0" in result.stdout
    assert validate_snapshot(snapshot) == 0
    with SQLiteDB(path) as db:
        # Hold a connection open to ensure committed changes remain in the WAL.
        connection = connect(path)
        try:
            connection.execute("PRAGMA wal_autocheckpoint = 0")
            with db.write() as tx:
                tx.connection.execute("CREATE TABLE demo (value TEXT)")
                tx.connection.execute("INSERT INTO demo VALUES (?)", ("from WAL",))
            assert (tmp_path / "db-wal").stat().st_size > 0
            result = cli("backup", path, snapshot)
            assert result.returncode == 0, result.stderr
            assert validate_snapshot(snapshot) == tx.revision == 1
            result = cli("migrate", path, snapshot)
            assert result.returncode == 1 and "stop the runtime" in result.stderr
            result = cli("restore", path, snapshot)
            assert result.returncode == 1 and "stop the runtime" in result.stderr
        finally:
            connection.close()
    original = hashlib.sha256(snapshot.read_bytes()).digest()
    target = tmp_path / "restored"
    result = cli("restore", target, snapshot)
    assert result.returncode == 0, result.stderr
    assert hashlib.sha256(snapshot.read_bytes()).digest() == original
    with SQLiteDB(target) as db, db.read() as connection:
        assert db.revision == 1
        assert connection.execute("SELECT value FROM demo").fetchall() == [
            ("from WAL",)
        ]
    result = cli("migrate", target, tmp_path / "migrated")
    assert result.returncode == 0, result.stderr
    assert validate_snapshot(tmp_path / "migrated") == 1


def test_init_refuses_overwrite_and_startup_never_creates(tmp_path):
    path, snapshot = tmp_path / "db", tmp_path / "snapshot"
    main(["init", "--db", str(path), "--snapshot", str(snapshot)])
    original = path.read_bytes()
    with pytest.raises(SystemExit) as exc:
        main(["init", "--db", str(path), "--snapshot", str(snapshot)])
    assert exc.value.code == 1 and path.read_bytes() == original
    with pytest.raises(FileNotFoundError):
        SQLiteDB(tmp_path / "missing")
    with pytest.raises(sqlite3.OperationalError):
        migrate(tmp_path / "missing", snapshot)
    assert not (tmp_path / "missing").exists()


@pytest.mark.parametrize(
    "invalid",
    ["missing", "corrupt", "future", "schema", "revision", "foreign-key", "sidecar"],
)
def test_invalid_snapshot_fails_closed_without_changing_source(tmp_path, invalid):
    path, snapshot, target = (
        tmp_path / "db",
        tmp_path / "snapshot",
        tmp_path / "restored",
    )
    main(["init", "--db", str(path), "--snapshot", str(snapshot)])
    if invalid == "missing":
        snapshot.unlink()
    elif invalid == "corrupt":
        snapshot.write_bytes(b"not a database")
    elif invalid == "sidecar":
        (tmp_path / "snapshot-wal").write_bytes(b"pending")
    else:
        connection = sqlite3.connect(snapshot, isolation_level=None)
        if invalid == "future":
            connection.execute("PRAGMA user_version = 999")
        elif invalid == "schema":
            connection.execute("DROP TABLE runtime_metadata")
        elif invalid == "revision":
            connection.execute("PRAGMA ignore_check_constraints = ON")
            connection.execute("UPDATE runtime_metadata SET revision = -1")
        else:
            connection.execute("CREATE TABLE parent (id INTEGER PRIMARY KEY)")
            connection.execute("CREATE TABLE child (id INTEGER REFERENCES parent(id))")
            connection.execute("INSERT INTO child VALUES (999)")
        connection.close()
    original = snapshot.read_bytes() if snapshot.exists() else None
    with pytest.raises((InvalidDatabase, FileNotFoundError)):
        restore(snapshot, target)
    assert not target.exists()
    assert (snapshot.read_bytes() if snapshot.exists() else None) == original


def test_restore_requires_empty_target_and_preserves_existing_state(tmp_path):
    path, snapshot = tmp_path / "db", tmp_path / "snapshot"
    main(["init", "--db", str(path), "--snapshot", str(snapshot)])
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        restore(snapshot, path)
    assert path.read_bytes() == original
    with SQLiteDB(path):
        with pytest.raises(RuntimeError, match="stop the runtime"):
            restore(snapshot, path)
        with pytest.raises(RuntimeError, match="stop the runtime"):
            migrate(path, snapshot)


def test_runtime_rejects_unversioned_state(tmp_path):
    path = tmp_path / "db"
    path.touch()
    with pytest.raises(InvalidDatabase):
        SQLiteDB(path)
    with pytest.raises(FileExistsError):
        initialize(path)


def test_migrate_does_not_initialize_an_empty_file(tmp_path):
    path = tmp_path / "db"
    path.touch()
    with pytest.raises(InvalidDatabase, match="uninitialized"):
        migrate(path, tmp_path / "snapshot")
    assert not (tmp_path / "snapshot").exists()


def test_snapshot_rejects_wal_header_without_sidecars(tmp_path):
    path, snapshot = tmp_path / "db", tmp_path / "snapshot"
    main(["init", "--db", str(path), "--snapshot", str(snapshot)])
    connection = sqlite3.connect(snapshot)
    connection.execute("PRAGMA journal_mode = WAL")
    connection.close()
    with pytest.raises(InvalidDatabase, match="WAL-dependent"):
        validate_snapshot(snapshot)
