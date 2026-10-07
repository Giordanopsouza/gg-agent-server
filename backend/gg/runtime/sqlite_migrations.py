"""Sequential, atomic SQLite schema migrations; no legacy data imports."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


class InvalidDatabase(ValueError):
    """Missing, incompatible, or incomplete runtime state."""


METADATA_SQL = """CREATE TABLE runtime_metadata (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    revision INTEGER NOT NULL CHECK (typeof(revision) = 'integer' AND revision >= 0)
)"""


@dataclass(frozen=True)
class Migration:
    version: int
    statements: tuple[str, ...]


MIGRATIONS = (
    Migration(1, (METADATA_SQL, "INSERT INTO runtime_metadata VALUES (1, 0)")),
)
SCHEMA_VERSION = MIGRATIONS[-1].version


def validate_schema(
    connection: sqlite3.Connection, *, version: int = SCHEMA_VERSION
) -> int:
    actual = connection.execute("PRAGMA user_version").fetchone()[0]
    if actual != version or actual < 1:
        raise InvalidDatabase(f"schema version {actual}; expected {version}")
    schema = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
        ("runtime_metadata",),
    ).fetchone()
    if schema is None or " ".join(schema[0].split()) != " ".join(METADATA_SQL.split()):
        raise InvalidDatabase("missing or incompatible runtime metadata schema")
    rows = connection.execute(
        "SELECT singleton, revision FROM runtime_metadata"
    ).fetchall()
    if (
        len(rows) != 1
        or rows[0][0] != 1
        or type(rows[0][1]) is not int
        or rows[0][1] < 0
    ):
        raise InvalidDatabase("invalid runtime revision")
    return rows[0][1]


def apply_migrations(
    connection: sqlite3.Connection, migrations: tuple[Migration, ...] = MIGRATIONS
) -> None:
    """Each version and its schema commit together; failed steps fully roll back."""
    if not migrations or [m.version for m in migrations] != list(
        range(1, len(migrations) + 1)
    ):
        raise InvalidDatabase("migrations must be sequential starting at 1")
    current = connection.execute("PRAGMA user_version").fetchone()[0]
    if current > migrations[-1].version:
        raise InvalidDatabase(f"future schema version {current}")
    if current:
        validate_schema(connection, version=current)
    elif connection.execute("SELECT name FROM sqlite_master").fetchone() is not None:
        raise InvalidDatabase("unversioned or interrupted schema")
    for migration in migrations[current:]:
        connection.execute("BEGIN IMMEDIATE")
        try:
            for statement in migration.statements:
                # executescript implicitly commits; use individual statements.
                connection.execute(statement)
            if migration.version > 1:
                connection.execute(
                    "UPDATE runtime_metadata SET revision = revision + 1"
                )
            connection.execute(f"PRAGMA user_version = {migration.version}")
            validate_schema(connection, version=migration.version)
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
