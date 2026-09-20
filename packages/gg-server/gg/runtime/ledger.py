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

import os
import sqlite3
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from gg.sdk.publication import PublicationRecord, PublicationState
from gg.sdk.task_execution import AgentOutcome, CheckOutcome
from gg.sdk.tasks import TaskRecord, TaskState


# The schema version this runtime understands. A database reporting a higher
# version is from a future runtime and must fail startup explicitly rather
# than silently downgrade.
SUPPORTED_SCHEMA_VERSION = 4


class SandboxProviderState(StrEnum):
    """Provider state as last established by a provider operation."""

    CREATING = "creating"
    RUNNING = "running"
    STOPPED = "stopped"
    UNKNOWN = "unknown"


class ReservationPhase(StrEnum):
    """Capacity-owning phases for one background task."""

    STARTING = "starting"
    RUNNING = "running"
    FINALIZING = "finalizing"
    TERMINATION_PENDING = "termination_pending"
    UNRESOLVED_CREATION = "unresolved_creation"


@dataclass(frozen=True)
class ReservationRecord:
    """One durable capacity reservation."""

    task_id: str
    phase: ReservationPhase
    condition: str | None
    reserved_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class SandboxCreationRecord:
    """Private durable intent and ownership record for one task sandbox."""

    task_id: str
    deployment: str
    sandbox_name: str
    tags_json: str
    session_api_key: str
    provider_id: str | None
    provider_state: SandboxProviderState
    detail: str | None
    created_at: datetime
    updated_at: datetime


def _row_to_sandbox_record(row: sqlite3.Row) -> SandboxCreationRecord:
    return SandboxCreationRecord(
        task_id=row["task_id"],
        deployment=row["deployment"],
        sandbox_name=row["sandbox_name"],
        tags_json=row["tags_json"],
        session_api_key=row["session_api_key"],
        provider_id=row["provider_id"],
        provider_state=SandboxProviderState(row["provider_state"]),
        detail=row["detail"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _row_to_reservation(row: sqlite3.Row) -> ReservationRecord:
    return ReservationRecord(
        task_id=row["task_id"],
        phase=ReservationPhase(row["phase"]),
        condition=row["condition"],
        reserved_at=datetime.fromisoformat(row["reserved_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


def _row_to_publication(row: sqlite3.Row) -> PublicationRecord:
    draft = row["pr_draft"]
    return PublicationRecord(
        task_id=row["task_id"],
        repository=row["repository"],
        task_branch=row["task_branch"],
        base_ref=row["base_ref"],
        task_marker=row["task_marker"],
        state=PublicationState(row["state"]),
        commit_sha=row["commit_sha"],
        check_outcome=CheckOutcome(row["check_outcome"]),
        agent_outcome=AgentOutcome(row["agent_outcome"]),
        pr_number=row["pr_number"],
        pr_url=row["pr_url"],
        pr_draft=None if draft is None else bool(draft),
        pr_author=row["pr_author"],
        pr_state=row["pr_state"],
        detail=row["detail"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


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
        if self._db_path != ":memory:":
            # The v2 ledger contains sandbox session credentials; keep the
            # control-plane database private even under a permissive umask.
            os.chmod(self._db_path, 0o600)
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
                if actual > self._expected_schema_version:
                    raise RuntimeError(
                        f"unsupported task ledger schema version {actual}; "
                        f"this runtime supports {self._expected_schema_version}"
                    )
                if actual < 1:
                    raise RuntimeError(
                        f"unsupported task ledger schema version {actual}"
                    )

            actual = int(
                self._conn.execute(
                    "SELECT value FROM schema_meta WHERE key = 'schema_version'"
                ).fetchone()["value"]
            )
            if actual < 2 <= self._expected_schema_version:
                self._conn.execute("BEGIN IMMEDIATE")
                try:
                    self._create_sandbox_schema()
                    self._conn.execute(
                        "UPDATE schema_meta SET value = '2' "
                        "WHERE key = 'schema_version'"
                    )
                    self._conn.execute("COMMIT")
                except Exception:
                    self._conn.execute("ROLLBACK")
                    raise

            actual = int(
                self._conn.execute(
                    "SELECT value FROM schema_meta WHERE key = 'schema_version'"
                ).fetchone()["value"]
            )
            if actual < 3 <= self._expected_schema_version:
                self._conn.execute("BEGIN IMMEDIATE")
                try:
                    self._create_reservation_schema()
                    self._conn.execute(
                        "UPDATE schema_meta SET value = '3' "
                        "WHERE key = 'schema_version'"
                    )
                    self._conn.execute("COMMIT")
                except Exception:
                    self._conn.execute("ROLLBACK")
                    raise

            actual = int(
                self._conn.execute(
                    "SELECT value FROM schema_meta WHERE key = 'schema_version'"
                ).fetchone()["value"]
            )
            if actual < 4 <= self._expected_schema_version:
                self._conn.execute("BEGIN IMMEDIATE")
                try:
                    self._create_publication_schema()
                    self._conn.execute(
                        "UPDATE schema_meta SET value = '4' "
                        "WHERE key = 'schema_version'"
                    )
                    self._conn.execute("COMMIT")
                except Exception:
                    self._conn.execute("ROLLBACK")
                    raise

            if self._expected_schema_version >= 2:
                self._create_sandbox_schema()
            if self._expected_schema_version >= 3:
                self._create_reservation_schema()
            if self._expected_schema_version >= 4:
                self._create_publication_schema()

    def _create_sandbox_schema(self) -> None:
        assert self._conn is not None
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sandbox_creations (
                task_id TEXT PRIMARY KEY,
                deployment TEXT NOT NULL,
                sandbox_name TEXT NOT NULL,
                tags_json TEXT NOT NULL,
                session_api_key TEXT NOT NULL,
                provider_id TEXT,
                provider_state TEXT NOT NULL,
                detail TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (task_id) REFERENCES tasks(id)
            )
            """
        )
        self._conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_sandbox_name "
            "ON sandbox_creations(deployment, sandbox_name)"
        )

    def _create_reservation_schema(self) -> None:
        assert self._conn is not None
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS task_reservations (
                task_id TEXT PRIMARY KEY,
                phase TEXT NOT NULL,
                condition TEXT,
                reserved_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (task_id) REFERENCES tasks(id)
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_reservations_reserved_at "
            "ON task_reservations(reserved_at)"
        )
        # A v2 ledger could contain lifecycle intents created before durable
        # reservations existed. Recover all non-stopped ownership so migration
        # cannot accidentally make that provider capacity available twice.
        self._conn.execute(
            """
            INSERT OR IGNORE INTO task_reservations (
                task_id, phase, condition, reserved_at, updated_at
            )
            SELECT
                task_id,
                CASE provider_state
                    WHEN 'running' THEN ?
                    WHEN 'unknown' THEN ?
                    ELSE ?
                END,
                CASE WHEN provider_state = 'unknown' THEN detail ELSE NULL END,
                created_at,
                updated_at
            FROM sandbox_creations
            WHERE provider_state != 'stopped'
            """,
            (
                ReservationPhase.RUNNING.value,
                ReservationPhase.UNRESOLVED_CREATION.value,
                ReservationPhase.STARTING.value,
            ),
        )
        self._conn.execute(
            """
            UPDATE tasks
            SET state = CASE
                WHEN (SELECT phase FROM task_reservations
                      WHERE task_id = tasks.id) = ? THEN ?
                ELSE ?
            END
            WHERE state = ?
              AND id IN (SELECT task_id FROM task_reservations)
            """,
            (
                ReservationPhase.RUNNING.value,
                TaskState.RUNNING.value,
                TaskState.STARTING.value,
                TaskState.QUEUED.value,
            ),
        )

    def _create_publication_schema(self) -> None:
        assert self._conn is not None
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS publication_intents (
                task_id TEXT PRIMARY KEY,
                repository TEXT NOT NULL,
                task_branch TEXT NOT NULL,
                base_ref TEXT NOT NULL,
                task_marker TEXT NOT NULL,
                commit_sha TEXT,
                state TEXT NOT NULL,
                check_outcome TEXT NOT NULL,
                agent_outcome TEXT NOT NULL,
                pr_number INTEGER,
                pr_url TEXT,
                pr_draft INTEGER,
                pr_author TEXT,
                pr_state TEXT,
                detail TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (task_id) REFERENCES tasks(id)
            )
            """
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
    def record_base_sha(self, task_id: str, base_sha: str) -> TaskRecord:
        """Persist the resolved starting revision for one task."""

        assert self._conn is not None
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                now = _utcnow_iso()
                self._conn.execute(
                    "UPDATE tasks SET base_sha = ?, updated_at = ? WHERE id = ?",
                    (base_sha, now, task_id),
                )
                if self._conn.execute("SELECT changes()").fetchone()[0] != 1:
                    raise KeyError(f"no task {task_id}")
                row = self._conn.execute(
                    "SELECT * FROM tasks WHERE id = ?", (task_id,)
                ).fetchone()
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
        assert row is not None
        return _row_to_record(row)

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

    def reserve_next(self, *, capacity: int) -> TaskRecord | None:
        """Atomically reserve the oldest queued task if capacity is available."""

        if not 1 <= capacity <= 10:
            raise ValueError("reservation capacity must be between 1 and 10")
        assert self._conn is not None
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                active = int(
                    self._conn.execute(
                        "SELECT COUNT(*) AS count FROM task_reservations"
                    ).fetchone()["count"]
                )
                if active >= capacity:
                    self._conn.execute("COMMIT")
                    return None
                row = self._conn.execute(
                    """
                    SELECT tasks.* FROM tasks
                    LEFT JOIN task_reservations
                        ON task_reservations.task_id = tasks.id
                    WHERE tasks.state = ? AND task_reservations.task_id IS NULL
                    ORDER BY tasks.seq ASC
                    LIMIT 1
                    """,
                    (TaskState.QUEUED.value,),
                ).fetchone()
                if row is None:
                    self._conn.execute("COMMIT")
                    return None
                now = _utcnow_iso()
                self._conn.execute(
                    """
                    INSERT INTO task_reservations (
                        task_id, phase, condition, reserved_at, updated_at
                    ) VALUES (?, ?, NULL, ?, ?)
                    """,
                    (row["id"], ReservationPhase.STARTING.value, now, now),
                )
                self._conn.execute(
                    "UPDATE tasks SET state = ?, updated_at = ? WHERE id = ?",
                    (TaskState.STARTING.value, now, row["id"]),
                )
                claimed = self._conn.execute(
                    "SELECT * FROM tasks WHERE id = ?", (row["id"],)
                ).fetchone()
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
        assert claimed is not None
        return _row_to_record(claimed)

    def list_reservations(self) -> list[ReservationRecord]:
        assert self._conn is not None
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM task_reservations ORDER BY reserved_at, task_id"
            ).fetchall()
        return [_row_to_reservation(row) for row in rows]

    def get_reservation(self, task_id: str) -> ReservationRecord | None:
        assert self._conn is not None
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM task_reservations WHERE task_id = ?", (task_id,)
            ).fetchone()
        return _row_to_reservation(row) if row is not None else None

    def update_reservation(
        self,
        task_id: str,
        *,
        phase: ReservationPhase,
        condition: str | None = None,
        task_state: TaskState | None = None,
    ) -> ReservationRecord:
        """Update reservation and public task state in one transaction."""

        assert self._conn is not None
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                now = _utcnow_iso()
                self._conn.execute(
                    """
                    UPDATE task_reservations
                    SET phase = ?, condition = ?, updated_at = ?
                    WHERE task_id = ?
                    """,
                    (phase.value, condition, now, task_id),
                )
                if self._conn.execute("SELECT changes()").fetchone()[0] != 1:
                    raise KeyError(f"no reservation for task {task_id}")
                if task_state is not None:
                    self._conn.execute(
                        "UPDATE tasks SET state = ?, updated_at = ? WHERE id = ?",
                        (task_state.value, now, task_id),
                    )
                row = self._conn.execute(
                    "SELECT * FROM task_reservations WHERE task_id = ?", (task_id,)
                ).fetchone()
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
        assert row is not None
        return _row_to_reservation(row)

    def release_reservation(
        self, task_id: str, *, cleanup_status: str = "confirmed_absent"
    ) -> None:
        """Release capacity only after provider absence has been confirmed."""

        assert self._conn is not None
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                now = _utcnow_iso()
                self._conn.execute(
                    "DELETE FROM task_reservations WHERE task_id = ?", (task_id,)
                )
                self._conn.execute(
                    """
                    UPDATE tasks
                    SET sandbox_cleanup_status = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (cleanup_status, now, task_id),
                )
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

    def mark_sandbox_lost(self, task_id: str, *, detail: str) -> None:
        """Fail execution without erasing previously captured task evidence."""

        assert self._conn is not None
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                now = _utcnow_iso()
                self._conn.execute(
                    """
                    UPDATE tasks
                    SET state = ?, outcome_detail = COALESCE(outcome_detail, ?),
                        sandbox_cleanup_status = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        TaskState.FAILED.value,
                        detail,
                        "confirmed_absent",
                        now,
                        task_id,
                    ),
                )
                self._conn.execute(
                    "DELETE FROM task_reservations WHERE task_id = ?", (task_id,)
                )
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

    def begin_sandbox_creation(
        self,
        *,
        task_id: str,
        deployment: str,
        sandbox_name: str,
        tags_json: str,
        session_api_key: str,
    ) -> tuple[SandboxCreationRecord, bool]:
        """Persist creation intent before any provider call."""

        assert self._conn is not None
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                existing = self._conn.execute(
                    "SELECT * FROM sandbox_creations WHERE task_id = ?", (task_id,)
                ).fetchone()
                if existing is not None:
                    self._conn.execute("COMMIT")
                    return _row_to_sandbox_record(existing), False
                now = _utcnow_iso()
                self._conn.execute(
                    """
                    INSERT INTO sandbox_creations (
                        task_id, deployment, sandbox_name, tags_json,
                        session_api_key, provider_id, provider_state, detail,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, NULL, ?, NULL, ?, ?)
                    """,
                    (
                        task_id,
                        deployment,
                        sandbox_name,
                        tags_json,
                        session_api_key,
                        SandboxProviderState.CREATING.value,
                        now,
                        now,
                    ),
                )
                row = self._conn.execute(
                    "SELECT * FROM sandbox_creations WHERE task_id = ?", (task_id,)
                ).fetchone()
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
        assert row is not None
        return _row_to_sandbox_record(row), True

    def get_sandbox_creation(self, task_id: str) -> SandboxCreationRecord | None:
        assert self._conn is not None
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM sandbox_creations WHERE task_id = ?", (task_id,)
            ).fetchone()
        return _row_to_sandbox_record(row) if row is not None else None

    def update_sandbox_creation(
        self,
        task_id: str,
        *,
        provider_id: str | None = None,
        provider_state: SandboxProviderState,
        detail: str | None = None,
    ) -> SandboxCreationRecord:
        """Record provider identity/state without exposing stored credentials."""

        assert self._conn is not None
        with self._lock:
            now = _utcnow_iso()
            if provider_id is None:
                self._conn.execute(
                    """
                    UPDATE sandbox_creations
                    SET provider_state = ?, detail = ?, updated_at = ?
                    WHERE task_id = ?
                    """,
                    (provider_state.value, detail, now, task_id),
                )
            else:
                self._conn.execute(
                    """
                    UPDATE sandbox_creations
                    SET provider_id = ?, provider_state = ?, detail = ?, updated_at = ?
                    WHERE task_id = ?
                    """,
                    (provider_id, provider_state.value, detail, now, task_id),
                )
            row = self._conn.execute(
                "SELECT * FROM sandbox_creations WHERE task_id = ?", (task_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"no sandbox creation intent for task {task_id}")
        return _row_to_sandbox_record(row)

    def begin_publication(
        self,
        *,
        task_id: str,
        repository: str,
        task_branch: str,
        base_ref: str,
        task_marker: str,
        commit_sha: str | None,
        check_outcome: CheckOutcome,
        agent_outcome: AgentOutcome,
        state: PublicationState = PublicationState.PENDING,
        detail: str | None = None,
    ) -> tuple[PublicationRecord, bool]:
        """Persist publication identity before push/create side effects."""

        assert self._conn is not None
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                existing = self._conn.execute(
                    "SELECT * FROM publication_intents WHERE task_id = ?",
                    (task_id,),
                ).fetchone()
                if existing is not None:
                    record = _row_to_publication(existing)
                    if (
                        record.repository != repository
                        or record.task_branch != task_branch
                        or record.base_ref != base_ref
                        or record.task_marker != task_marker
                    ):
                        self._conn.execute("COMMIT")
                        raise PublicationIdentityError(
                            "existing publication identity does not match "
                            f"task {task_id}"
                        )
                    if (
                        record.commit_sha is not None
                        and commit_sha is not None
                        and record.commit_sha != commit_sha
                    ):
                        self._conn.execute("COMMIT")
                        raise PublicationIdentityError(
                            f"existing publication commit does not match task {task_id}"
                        )
                    self._conn.execute("COMMIT")
                    return record, False
                now = _utcnow_iso()
                self._conn.execute(
                    """
                    INSERT INTO publication_intents (
                        task_id, repository, task_branch, base_ref, task_marker,
                        commit_sha, state, check_outcome, agent_outcome,
                        pr_number, pr_url, pr_draft, pr_author, pr_state,
                        detail, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL,
                              NULL, ?, ?, ?)
                    """,
                    (
                        task_id,
                        repository,
                        task_branch,
                        base_ref,
                        task_marker,
                        commit_sha,
                        state.value,
                        check_outcome.value,
                        agent_outcome.value,
                        detail,
                        now,
                        now,
                    ),
                )
                row = self._conn.execute(
                    "SELECT * FROM publication_intents WHERE task_id = ?",
                    (task_id,),
                ).fetchone()
                self._conn.execute("COMMIT")
            except PublicationIdentityError:
                raise
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
        assert row is not None
        return _row_to_publication(row), True

    def get_publication(self, task_id: str) -> PublicationRecord | None:
        assert self._conn is not None
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM publication_intents WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        return _row_to_publication(row) if row is not None else None

    def update_publication(
        self,
        task_id: str,
        *,
        state: PublicationState,
        commit_sha: str | None = None,
        pr_number: int | None = None,
        pr_url: str | None = None,
        pr_draft: bool | None = None,
        pr_author: str | None = None,
        pr_state: str | None = None,
        detail: str | None = None,
        check_status: str | None = None,
        outcome_detail: str | None = None,
    ) -> PublicationRecord:
        """Record publication progress without storing credentials."""

        assert self._conn is not None
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                now = _utcnow_iso()
                current = self._conn.execute(
                    "SELECT * FROM publication_intents WHERE task_id = ?",
                    (task_id,),
                ).fetchone()
                if current is None:
                    raise KeyError(f"no publication intent for task {task_id}")
                draft_value = current["pr_draft"] if pr_draft is None else int(pr_draft)
                self._conn.execute(
                    """
                    UPDATE publication_intents
                    SET state = ?,
                        commit_sha = COALESCE(?, commit_sha),
                        pr_number = COALESCE(?, pr_number),
                        pr_url = COALESCE(?, pr_url),
                        pr_draft = ?,
                        pr_author = COALESCE(?, pr_author),
                        pr_state = COALESCE(?, pr_state),
                        detail = ?,
                        updated_at = ?
                    WHERE task_id = ?
                    """,
                    (
                        state.value,
                        commit_sha,
                        pr_number,
                        pr_url,
                        draft_value,
                        pr_author,
                        pr_state,
                        detail,
                        now,
                        task_id,
                    ),
                )
                if check_status is not None or outcome_detail is not None:
                    self._conn.execute(
                        """
                        UPDATE tasks
                        SET check_status = COALESCE(?, check_status),
                            outcome_detail = COALESCE(?, outcome_detail),
                            updated_at = ?
                        WHERE id = ?
                        """,
                        (check_status, outcome_detail, now, task_id),
                    )
                row = self._conn.execute(
                    "SELECT * FROM publication_intents WHERE task_id = ?",
                    (task_id,),
                ).fetchone()
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
        assert row is not None
        return _row_to_publication(row)


class PublicationIdentityError(RuntimeError):
    """A task's stored publication identity does not match a retry."""


__all__ = [
    "SUPPORTED_SCHEMA_VERSION",
    "PublicationIdentityError",
    "ReservationPhase",
    "ReservationRecord",
    "SandboxCreationRecord",
    "SandboxProviderState",
    "TaskLedger",
]
