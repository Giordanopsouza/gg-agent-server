"""SQLite-backed durable ledger for background tasks.

Owns schema versioning, FIFO sequence assignment, idempotency, and the
transactional submission of one task. The ledger never imports ``gg.server``;
it shares only frozen SDK models across the package boundary.

Concurrency: a single connection guarded by a lock. Writers open
``BEGIN IMMEDIATE`` so concurrent submissions serialize at the SQLite level
and never expose a partially submitted task. ``seq`` is monotonically assigned
inside the same transaction that inserts the row.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from gg.sdk.tasks import TaskRecord, TaskState


# The schema version this runtime understands. A database reporting a higher
# version is from a future runtime and must fail startup explicitly rather
# than silently downgrade.
SUPPORTED_SCHEMA_VERSION = 1


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


def _row_to_record(row: sqlite3.Row) -> TaskRecord:
    return TaskRecord(
        id=row["id"],
        seq=row["seq"],
        state=TaskState(row["state"]),
        idempotency_key=row["idempotency_key"],
        repository=row["repository"],
        prompt=row["prompt"],
        base_ref=row["base_ref"],
        base_sha=row["base_sha"],
        retry_of=row["retry_of"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        outcome_detail=row["outcome_detail"],
        check_status=row["check_status"],
        sandbox_cleanup_status=row["sandbox_cleanup_status"],
    )


class TaskLedger:
    """Durable SQLite ledger for background tasks."""

    def __init__(
        self, *, db_path: str, schema_version: int = SUPPORTED_SCHEMA_VERSION
    ) -> None:
        self._db_path = db_path
        self._expected_schema_version = schema_version
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None

    # Open the database, initialize schema, and verify the schema version.
    def open(self) -> None:
        if self._conn is not None:
            return
        if self._db_path != ":memory:":
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(
            self._db_path, isolation_level=None, check_same_thread=False
        )
        conn.row_factory = sqlite3.Row
        # WAL improves crash safety and allows readers during writes.
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            # :memory: databases do not support WAL; fall back silently.
            pass
        conn.execute("PRAGMA foreign_keys=ON")
        self._conn = conn
        self._ensure_schema()

    # Close the database connection; safe to call once.
    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    # Context-manager support for tests and lifespan wiring.
    def __enter__(self) -> TaskLedger:
        self.open()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # Create the schema if absent and verify the recorded schema version.
    def _ensure_schema(self) -> None:
        assert self._conn is not None
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            row = self._conn.execute(
                "SELECT value FROM schema_meta WHERE key = 'schema_version'"
            ).fetchone()
            if row is None:
                self._conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS tasks (
                        id TEXT PRIMARY KEY,
                        seq INTEGER NOT NULL UNIQUE,
                        state TEXT NOT NULL,
                        idempotency_key TEXT NOT NULL UNIQUE,
                        repository TEXT NOT NULL,
                        prompt TEXT NOT NULL,
                        base_ref TEXT,
                        base_sha TEXT,
                        retry_of TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        outcome_detail TEXT,
                        check_status TEXT,
                        sandbox_cleanup_status TEXT
                    )
                    """
                )
                self._conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_tasks_seq ON tasks(seq)"
                )
                self._conn.execute(
                    "INSERT INTO schema_meta (key, value) VALUES (?, ?)",
                    ("schema_version", str(self._expected_schema_version)),
                )
            else:
                actual = int(row["value"])
                if actual != self._expected_schema_version:
                    raise RuntimeError(
                        f"unsupported task ledger schema version {actual}; "
                        f"this runtime supports {self._expected_schema_version}"
                    )

    # Atomically insert a new queued task or return an existing one by
    # idempotency key. Returns (record, created) where created is False when
    # the idempotency key already existed.
    def submit(
        self,
        *,
        idempotency_key: str,
        repository: str,
        prompt: str,
        base_ref: str | None,
        retry_of: str | None,
    ) -> tuple[TaskRecord, bool]:
        assert self._conn is not None
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                existing = self._conn.execute(
                    "SELECT * FROM tasks WHERE idempotency_key = ?",
                    (idempotency_key,),
                ).fetchone()
                if existing is not None:
                    self._conn.execute("COMMIT")
                    return _row_to_record(existing), False

                seq_row = self._conn.execute(
                    "SELECT COALESCE(MAX(seq), 0) + 1 AS next_seq FROM tasks"
                ).fetchone()
                seq = int(seq_row["next_seq"])
                now = _utcnow_iso()
                task_id = str(uuid4())
                self._conn.execute(
                    """
                    INSERT INTO tasks (
                        id, seq, state, idempotency_key, repository, prompt,
                        base_ref, base_sha, retry_of, created_at, updated_at,
                        outcome_detail, check_status, sandbox_cleanup_status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, NULL, NULL, NULL)
                    """,
                    (
                        task_id,
                        seq,
                        TaskState.QUEUED.value,
                        idempotency_key,
                        repository,
                        prompt,
                        base_ref,
                        retry_of,
                        now,
                        now,
                    ),
                )
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
        return (
            TaskRecord(
                id=task_id,
                seq=seq,
                state=TaskState.QUEUED,
                idempotency_key=idempotency_key,
                repository=repository,
                prompt=prompt,
                base_ref=base_ref,
                retry_of=retry_of,
                created_at=datetime.fromisoformat(now),
                updated_at=datetime.fromisoformat(now),
            ),
            True,
        )

    # Return one task by id, or None.
    def get(self, task_id: str) -> TaskRecord | None:
        assert self._conn is not None
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
        return _row_to_record(row) if row is not None else None

    # Return all tasks in FIFO (seq) order.
    def list(self) -> list[TaskRecord]:
        assert self._conn is not None
        with self._lock:
            rows = self._conn.execute("SELECT * FROM tasks ORDER BY seq ASC").fetchall()
        return [_row_to_record(row) for row in rows]


__all__ = ["SUPPORTED_SCHEMA_VERSION", "TaskLedger"]
