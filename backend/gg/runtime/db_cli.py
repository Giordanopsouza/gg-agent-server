"""Local state operations: python -m gg.runtime.db_cli COMMAND --db PATH ...

Init/restore target a new path. Migrate/restore require the runtime stopped.
Use a separate local database and snapshot path (the latter may be on a Volume).
"""

from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path

from gg.runtime.checkpoints import (
    publish_connection_snapshot,
    publish_snapshot,
    validate_snapshot,
)
from gg.runtime.sqlite_db import SQLiteDB, connect, database_lease, initialize
from gg.runtime.sqlite_migrations import InvalidDatabase, apply_migrations


def migrate(path: Path, snapshot: Path) -> int:
    with database_lease(path, exclusive=True):
        connection = connect(path)
        try:
            if connection.execute("PRAGMA user_version").fetchone()[0] == 0:
                raise InvalidDatabase(
                    "uninitialized database; use explicit init on a new path"
                )
            apply_migrations(connection)
            return publish_connection_snapshot(connection, snapshot)
        finally:
            connection.close()


def restore(snapshot: Path, destination: Path, *, allow_older: bool = False) -> int:
    """Never edit the source or overwrite state. Restore into a fresh location."""
    revision = validate_snapshot(snapshot, allow_older=allow_older)
    destination = destination.resolve()
    with database_lease(destination, exclusive=True):
        if destination.exists() or any(
            Path(f"{destination}{s}").exists() for s in ("-wal", "-shm", "-journal")
        ):
            raise FileExistsError(destination)
        descriptor, filename = tempfile.mkstemp(
            prefix=f".{destination.name}-", dir=destination.parent
        )
        os.close(descriptor)
        temporary = Path(filename)
        try:
            shutil.copyfile(snapshot, temporary)
            if validate_snapshot(temporary, allow_older=allow_older) != revision:
                raise InvalidDatabase("source snapshot changed during restore")
            with temporary.open("rb") as source:
                os.fsync(source.fileno())
            # link refuses an existing target even if created after the check.
            os.link(temporary, destination)
            directory = os.open(destination.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            temporary.unlink(missing_ok=True)
    return revision


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("init", "migrate", "backup", "restore"))
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "restore":
            revision = restore(args.snapshot, args.db)
        elif args.command == "migrate":
            revision = migrate(args.db, args.snapshot)
        else:
            if args.command == "init":
                if args.snapshot.exists():
                    raise FileExistsError(args.snapshot)
                initialize(args.db)
            with SQLiteDB(args.db) as db:
                revision = publish_snapshot(db, args.snapshot)
    except (OSError, ValueError, RuntimeError, sqlite3.DatabaseError) as exc:
        parser.exit(1, f"{args.command} failed: {exc}\n")
    print(f"{args.command}: revision={revision}")


if __name__ == "__main__":
    main()
