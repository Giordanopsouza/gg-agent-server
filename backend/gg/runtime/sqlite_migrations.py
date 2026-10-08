"""Sequential, atomic SQLite schema migrations; no legacy data imports."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


class InvalidDatabase(ValueError):
    """Missing, incompatible, or incomplete runtime state."""


METADATA_SQL = """
            CREATE TABLE runtime_metadata ( singleton INTEGER PRIMARY KEY CHECK
            (singleton = 1), revision INTEGER NOT NULL CHECK (typeof(revision) =
            'integer' AND revision >= 0) )
            """


@dataclass(frozen=True)
class Migration:
    version: int
    statements: tuple[str, ...]


MIGRATIONS = (
    Migration(1, (METADATA_SQL, "INSERT INTO runtime_metadata VALUES (1, 0)")),
    Migration(
        2,
        (
            """
            CREATE TABLE ledger_counters (name TEXT PRIMARY KEY NOT NULL, value
            INTEGER NOT NULL CHECK (value >= 0)) STRICT
            """,
            "INSERT INTO ledger_counters VALUES ('task_seq', 0)",
            """
            CREATE TABLE tasks ( id TEXT PRIMARY KEY NOT NULL, seq INTEGER
            UNIQUE NOT NULL CHECK (seq > 0), state TEXT NOT NULL CHECK (state IN
            ('queued','starting','running','idle','sleeping','finalizing','completed','failed','cancelled')),
            idempotency_key TEXT NOT NULL, owner_id TEXT, repository TEXT NOT
            NULL, prompt TEXT NOT NULL, base_ref TEXT, base_sha TEXT, retry_of
            TEXT, model TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT
            NOT NULL, outcome_detail TEXT, check_status TEXT,
            sandbox_cleanup_status TEXT, payload_expired INTEGER NOT NULL
            DEFAULT 0 CHECK (payload_expired IN (0,1)), workspace_expired
            INTEGER NOT NULL DEFAULT 0 CHECK (workspace_expired IN (0,1)),
            workspace_last_activity_at TEXT ) STRICT
            """,
            """
            CREATE UNIQUE INDEX tasks_admin_key ON tasks(idempotency_key) WHERE
            owner_id IS NULL
            """,
            """
            CREATE UNIQUE INDEX tasks_owner_key ON tasks(owner_id,
            idempotency_key) WHERE owner_id IS NOT NULL
            """,
            "CREATE INDEX tasks_owner_seq ON tasks(owner_id, seq)",
            """
            CREATE TABLE task_reservations ( task_id TEXT PRIMARY KEY NOT NULL
            REFERENCES tasks(id), phase TEXT NOT NULL CHECK (phase IN
            ('starting','running','finalizing','termination_pending','unresolved_creation')),
            condition TEXT, reserved_at TEXT NOT NULL, updated_at TEXT NOT NULL
            ) STRICT
            """,
        ),
    ),
    Migration(
        3,
        (
            """
            CREATE TABLE sandbox_creations ( task_id TEXT PRIMARY KEY NOT NULL
            REFERENCES tasks(id), deployment TEXT NOT NULL, sandbox_name TEXT
            NOT NULL, tags_json TEXT NOT NULL CHECK (json_valid(tags_json)),
            session_api_key TEXT NOT NULL, credential_version INTEGER CHECK
            (credential_version > 0), provider_id TEXT, provider_state TEXT NOT
            NULL CHECK (provider_state IN
            ('creating','running','stopped','unknown')), detail TEXT, created_at
            TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(deployment,
            sandbox_name) ) STRICT
            """,
            """
            CREATE TABLE task_supervisions ( task_id TEXT PRIMARY KEY NOT NULL
            REFERENCES tasks(id), execution_id TEXT NOT NULL, task_branch TEXT
            NOT NULL, start_key TEXT UNIQUE NOT NULL, conversation_id TEXT,
            cancel_requested INTEGER NOT NULL DEFAULT 0 CHECK (cancel_requested
            IN (0,1)), tail_gap_possible INTEGER NOT NULL DEFAULT 0 CHECK
            (tail_gap_possible IN (0,1)), created_at TEXT NOT NULL, updated_at
            TEXT NOT NULL ) STRICT
            """,
            """
            CREATE TABLE publication_intents ( task_id TEXT PRIMARY KEY NOT NULL
            REFERENCES tasks(id), repository TEXT NOT NULL, task_branch TEXT NOT
            NULL, base_ref TEXT NOT NULL, task_marker TEXT NOT NULL, commit_sha
            TEXT, state TEXT NOT NULL, check_outcome TEXT NOT NULL,
            agent_outcome TEXT NOT NULL, pr_number INTEGER, pr_url TEXT,
            pr_draft INTEGER CHECK (pr_draft IN (0,1)), pr_author TEXT, pr_state
            TEXT, detail TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT
            NULL ) STRICT
            """,
            """
            CREATE TABLE task_message_receipts ( task_id TEXT NOT NULL
            REFERENCES tasks(id), message_id TEXT NOT NULL, content TEXT NOT
            NULL, status TEXT NOT NULL, detail TEXT, created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL, PRIMARY KEY(task_id, message_id) ) STRICT
            """,
        ),
    ),
    Migration(
        4,
        (
            """
            CREATE TABLE task_event_counters ( task_id TEXT PRIMARY KEY NOT
            NULL, value INTEGER NOT NULL CHECK (value >= 0) ) STRICT
            """,
            """
            CREATE TABLE task_event_identities ( task_id TEXT NOT NULL,
            source_id TEXT NOT NULL, source_seq INTEGER NOT NULL, cursor_seq
            INTEGER NOT NULL CHECK (cursor_seq > 0), PRIMARY KEY(task_id,
            source_id, source_seq), UNIQUE(task_id, cursor_seq) ) STRICT
            """,
            """
            CREATE TABLE task_event_copies ( task_id TEXT NOT NULL REFERENCES
            tasks(id), cursor_seq INTEGER NOT NULL, source_id TEXT NOT NULL,
            source_seq INTEGER NOT NULL, event_json TEXT NOT NULL CHECK
            (json_valid(event_json)), created_at TEXT NOT NULL, PRIMARY
            KEY(task_id, cursor_seq), UNIQUE(task_id, source_id, source_seq) )
            STRICT
            """,
            """
            CREATE TABLE task_results ( task_id TEXT PRIMARY KEY NOT NULL
            REFERENCES tasks(id), execution_id TEXT, manifest_json TEXT CHECK
            (json_valid(manifest_json)), evidence_complete INTEGER NOT NULL
            CHECK (evidence_complete IN (0,1)), evidence_detail TEXT,
            archived_at TEXT ) STRICT
            """,
            """
            CREATE TABLE retention_tombstones ( task_id TEXT PRIMARY KEY NOT
            NULL, remote_effect_json TEXT CHECK
            (json_valid(remote_effect_json)), expires_at TEXT NOT NULL ) STRICT
            """,
            """
            CREATE TABLE task_idempotency ( task_id TEXT PRIMARY KEY NOT NULL,
            owner_id TEXT, idempotency_key TEXT NOT NULL, seq INTEGER UNIQUE NOT
            NULL, terminal_state TEXT NOT NULL, model TEXT NOT NULL, created_at
            TEXT NOT NULL, updated_at TEXT NOT NULL ) STRICT
            """,
            """
            CREATE UNIQUE INDEX idempotency_admin_key ON
            task_idempotency(idempotency_key) WHERE owner_id IS NULL
            """,
            """
            CREATE UNIQUE INDEX idempotency_owner_key ON
            task_idempotency(owner_id, idempotency_key) WHERE owner_id IS NOT
            NULL
            """,
        ),
    ),
    Migration(
        5,
        (
            """CREATE TABLE local_users (id TEXT PRIMARY KEY NOT NULL,
        google_sub TEXT UNIQUE NOT NULL, email TEXT NOT NULL) STRICT""",
            """CREATE TABLE local_sessions (token_hash TEXT PRIMARY KEY NOT NULL,
        owner_id TEXT NOT NULL REFERENCES local_users(id), expires_at INTEGER
        NOT NULL, revoked INTEGER NOT NULL DEFAULT 0 CHECK (revoked IN (0,1)))
        STRICT""",
        ),
    ),
    Migration(
        6,
        (
            """CREATE TABLE google_flows (state TEXT PRIMARY KEY NOT NULL,
        browser_hash TEXT NOT NULL, nonce TEXT NOT NULL, verifier TEXT NOT NULL,
        return_to TEXT NOT NULL, expires_at INTEGER NOT NULL,
        status TEXT NOT NULL CHECK (status IN
        ('pending','claimed','completed','failed')),
        session_hash TEXT REFERENCES local_sessions(token_hash),
        completion_revision INTEGER) STRICT""",
        ),
    ),
    Migration(
        7,
        (
            """CREATE TABLE openrouter_credentials (owner_id TEXT PRIMARY KEY NOT NULL
        REFERENCES local_users(id), ciphertext BLOB, mask TEXT,
        credential_version INTEGER NOT NULL CHECK (credential_version > 0),
        CHECK ((ciphertext IS NULL) = (mask IS NULL))) STRICT""",
        ),
    ),
    Migration(
        8,
        (
            """CREATE TABLE github_connections (owner_id TEXT PRIMARY KEY NOT NULL
        REFERENCES local_users(id), github_user_id INTEGER UNIQUE NOT NULL CHECK
        (github_user_id > 0), login TEXT NOT NULL, token_ciphertext BLOB,
        status TEXT NOT NULL CHECK (status IN
        ('connected','pending','revoked'))) STRICT""",
            """CREATE TABLE github_installations (owner_id TEXT NOT NULL REFERENCES
        github_connections(owner_id) ON DELETE CASCADE, installation_id INTEGER
        NOT NULL CHECK (installation_id > 0), account_login TEXT NOT NULL,
        account_type TEXT NOT NULL, status TEXT NOT NULL CHECK (status IN
        ('active','removed','suspended')), PRIMARY KEY(owner_id, installation_id))
        STRICT""",
            """CREATE TABLE github_oauth_flows (state_hash TEXT PRIMARY KEY NOT NULL,
        owner_id TEXT NOT NULL REFERENCES local_users(id), session_id TEXT NOT NULL
        REFERENCES local_sessions(token_hash), expires_at INTEGER NOT NULL) STRICT""",
            """CREATE TABLE github_webhook_deliveries (delivery_id TEXT
        PRIMARY KEY NOT NULL) STRICT""",
        ),
    ),
    Migration(
        9,
        (
            "CREATE INDEX tasks_state_seq ON tasks(state, seq)",
            """CREATE INDEX tasks_sleeping_expiry ON tasks(
                COALESCE(workspace_last_activity_at, updated_at), seq)
                WHERE state = 'sleeping' AND workspace_expired = 0""",
            """CREATE INDEX tasks_settlement ON tasks(outcome_detail)
                WHERE sandbox_cleanup_status = 'confirmed_absent'
                AND state NOT IN ('completed', 'cancelled')""",
            """CREATE INDEX reservations_order
                ON task_reservations(reserved_at, task_id)""",
        ),
    ),
    Migration(
        10,
        (
            """CREATE TABLE task_event_source_cursors (
                task_id TEXT NOT NULL, source_id TEXT NOT NULL,
                source_seq INTEGER NOT NULL CHECK (source_seq >= 0),
                PRIMARY KEY(task_id, source_id)) STRICT""",
        ),
    ),
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
    for migration in MIGRATIONS[1:version]:
        for statement in migration.statements:
            statement = statement.strip()
            if not statement.startswith("CREATE "):
                continue
            words = statement.split()
            kind = "index" if "INDEX" in words[:3] else "table"
            name = words[words.index(kind.upper()) + 1].split("(")[0]
            stored = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type = ? AND name = ?",
                (kind, name),
            ).fetchone()
            if stored is None or " ".join(stored[0].split()) != " ".join(
                statement.split()
            ):
                raise InvalidDatabase(f"missing or incompatible {name} schema")
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
