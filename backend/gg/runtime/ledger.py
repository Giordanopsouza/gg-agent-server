"""Postgres-backed durable task ledger for the control plane."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from sqlalchemy import Engine

from gg.runtime.postgres import RuntimePostgres
from gg.sdk.agent_backend import DEFAULT_PI_MODEL
from gg.sdk.domain import Event, MessageDeliveryStatus, MessageReceipt
from gg.sdk.publication import PublicationRecord, PublicationState
from gg.sdk.task_execution import AgentOutcome, CheckOutcome, TaskResultManifest
from gg.sdk.tasks import TaskRecord, TaskState


# The schema version this runtime understands. A database reporting a higher
# version is from a future runtime and must fail startup explicitly rather
# than silently downgrade.
SUPPORTED_SCHEMA_VERSION = 9

# Outcomes recorded only after the agent finished successfully. A later sandbox
# reconcile must not replace these with a failure.
_SETTLED_SUCCESS_OUTCOMES = frozenset(
    {"published", "no_changes", "checks_passed", "checks_not_run"}
)
_TERMINAL_TASK_STATES = frozenset(
    {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED}
)


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
class SupervisionRecord:
    """Persisted sandbox execution identity for one background task."""

    task_id: str
    execution_id: str
    task_branch: str
    start_key: str
    conversation_id: str | None
    cancel_requested: bool
    tail_gap_possible: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class TaskResultArchive:
    """Durable control-plane copy of one task's evidence manifest."""

    task_id: str
    execution_id: str | None
    manifest: TaskResultManifest | None
    evidence_complete: bool
    evidence_detail: str | None
    archived_at: datetime | None


@dataclass(frozen=True)
class SandboxCreationRecord:
    """Private durable intent and ownership record for one task sandbox."""

    task_id: str
    deployment: str
    sandbox_name: str
    tags_json: str
    session_api_key: str
    credential_version: int | None
    provider_id: str | None
    provider_state: SandboxProviderState
    detail: str | None
    created_at: datetime
    updated_at: datetime


def _row_to_sandbox_record(row: dict[str, Any]) -> SandboxCreationRecord:
    return SandboxCreationRecord(
        task_id=row["task_id"],
        deployment=row["deployment"],
        sandbox_name=row["sandbox_name"],
        tags_json=row["tags_json"],
        session_api_key=row["session_api_key"],
        credential_version=row["credential_version"],
        provider_id=row["provider_id"],
        provider_state=SandboxProviderState(row["provider_state"]),
        detail=row["detail"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _row_to_reservation(row: dict[str, Any]) -> ReservationRecord:
    return ReservationRecord(
        task_id=row["task_id"],
        phase=ReservationPhase(row["phase"]),
        condition=row["condition"],
        reserved_at=datetime.fromisoformat(row["reserved_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


def _row_to_publication(row: dict[str, Any]) -> PublicationRecord:
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


def _row_to_record(row: dict[str, Any]) -> TaskRecord:
    return TaskRecord(
        owner_id=row["owner_id"],
        id=row["id"],
        seq=row["seq"],
        state=TaskState(row["state"]),
        idempotency_key=row["idempotency_key"],
        repository=row["repository"] or None,
        prompt=row["prompt"],
        base_ref=row["base_ref"],
        base_sha=row["base_sha"],
        retry_of=row["retry_of"],
        model=row["model"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        outcome_detail=row["outcome_detail"],
        check_status=row["check_status"],
        sandbox_cleanup_status=row["sandbox_cleanup_status"],
        payload_expired=bool(row["payload_expired"])
        if "payload_expired" in row.keys()
        else False,
        workspace_expired=bool(row["workspace_expired"])
        if "workspace_expired" in row.keys()
        else False,
        workspace_last_activity_at=(
            datetime.fromisoformat(row["workspace_last_activity_at"])
            if "workspace_last_activity_at" in row.keys()
            and row["workspace_last_activity_at"]
            else None
        ),
    )


class TaskLedger:
    """Durable runtime ledger stored in the private Postgres schema."""

    def __init__(self, database: RuntimePostgres) -> None:
        self._database = database
        self._engine: Engine = database.engine()
        self._lock = threading.Lock()
        self._conn: Any | None = None

    @property
    def engine(self) -> Engine:
        """The shared process engine used by other database-backed services."""
        return self._engine

    def open(self) -> None:
        if self._conn is not None:
            return
        connection = self._engine.raw_connection()
        connection.driver_connection.row_factory = dict_row
        connection.autocommit = True
        try:
            connection.execute(
                sql.SQL("SET search_path TO {}").format(
                    sql.Identifier(self._database.schema)
                )
            )
            self._conn = connection
            version = self._schema_version()
            if version != SUPPORTED_SCHEMA_VERSION:
                raise RuntimeError(
                    f"unsupported Postgres ledger schema version {version}; "
                    f"expected {SUPPORTED_SCHEMA_VERSION}"
                )
        except Exception:
            connection.close()
            self._engine.dispose()
            self._conn = None
            raise

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None
            self._engine.dispose()

    def __enter__(self) -> TaskLedger:
        self.open()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _begin_write(self) -> None:
        assert self._conn is not None
        self._conn.execute("BEGIN")
        # Serialize sequence, capacity, and publication decisions across workers.
        self._conn.execute("SELECT pg_advisory_xact_lock(780078)")

    def submit(
        self,
        *,
        idempotency_key: str,
        repository: str | None,
        prompt: str,
        base_ref: str | None,
        retry_of: str | None,
        model: str = DEFAULT_PI_MODEL,
        owner_id: UUID | None = None,
    ) -> tuple[TaskRecord, bool]:
        assert self._conn is not None
        with self._lock:
            self._begin_write()
            try:
                scope, scope_params = self._owner_scope(owner_id)
                existing = self._conn.execute(
                    f"SELECT * FROM tasks WHERE idempotency_key = %s AND {scope}",
                    (idempotency_key, *scope_params),
                ).fetchone()
                if existing is not None:
                    self._conn.execute("COMMIT")
                    return _row_to_record(existing), False
                tombstone = self._conn.execute(
                    "SELECT * FROM retention_tombstones "
                    f"WHERE idempotency_key = %s AND {scope}",
                    (idempotency_key, *scope_params),
                ).fetchone()
                if tombstone is not None:
                    self._conn.execute("COMMIT")
                    return self._record_from_tombstone(tombstone), False

                seq_row = self._conn.execute(
                    "SELECT COALESCE(MAX(seq), 0) + 1 AS next_seq FROM tasks"
                ).fetchone()
                seq = int(seq_row["next_seq"])
                now = _utcnow_iso()
                task_id = str(uuid4())
                self._conn.execute(
                    """
                    INSERT INTO tasks (
                        id, seq, state, idempotency_key, owner_id, repository,
                        prompt, base_ref, base_sha, retry_of, model,
                        created_at, updated_at,
                        outcome_detail, check_status, sandbox_cleanup_status
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, NULL,
                        %s, %s, %s, %s, NULL, NULL, NULL
                    )
                    """,
                    (
                        task_id,
                        seq,
                        TaskState.QUEUED.value,
                        idempotency_key,
                        owner_id,
                        repository or "",
                        prompt,
                        base_ref,
                        retry_of,
                        model,
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
                owner_id=owner_id,
                id=task_id,
                seq=seq,
                state=TaskState.QUEUED,
                idempotency_key=idempotency_key,
                repository=repository,
                prompt=prompt,
                base_ref=base_ref,
                retry_of=retry_of,
                model=model,
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
            self._begin_write()
            try:
                now = _utcnow_iso()
                updated = self._conn.execute(
                    "UPDATE tasks SET base_sha = %s, updated_at = %s WHERE id = %s",
                    (base_sha, now, task_id),
                )
                if updated.rowcount != 1:
                    raise KeyError(f"no task {task_id}")
                row = self._conn.execute(
                    "SELECT * FROM tasks WHERE id = %s", (task_id,)
                ).fetchone()
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
        assert row is not None
        return _row_to_record(row)

    @staticmethod
    def _owner_scope(owner_id: UUID | None) -> tuple[str, tuple[UUID, ...]]:
        if owner_id is None:
            return "owner_id IS NULL", ()
        return "owner_id = %s", (owner_id,)

    def get(self, task_id: str, *, owner_id: UUID | None = None) -> TaskRecord | None:
        assert self._conn is not None
        with self._lock:
            if owner_id is None:
                row = self._conn.execute(
                    "SELECT * FROM tasks WHERE id = %s", (task_id,)
                ).fetchone()
            else:
                row = self._conn.execute(
                    "SELECT * FROM tasks WHERE id = %s AND owner_id = %s",
                    (task_id, owner_id),
                ).fetchone()
        return _row_to_record(row) if row is not None else None

    # Return all tasks in FIFO (seq) order.
    def list(self, *, owner_id: UUID | None = None) -> list[TaskRecord]:
        assert self._conn is not None
        with self._lock:
            if owner_id is None:
                rows = self._conn.execute(
                    "SELECT * FROM tasks ORDER BY seq ASC"
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM tasks WHERE owner_id = %s ORDER BY seq ASC",
                    (owner_id,),
                ).fetchall()
        return [_row_to_record(row) for row in rows]

    def reserve_next(self, *, capacity: int) -> TaskRecord | None:
        """Atomically reserve the oldest queued task if capacity is available."""

        if not 1 <= capacity <= 10:
            raise ValueError("reservation capacity must be between 1 and 10")
        assert self._conn is not None
        with self._lock:
            self._begin_write()
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
                    WHERE tasks.state = %s AND task_reservations.task_id IS NULL
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
                    ) VALUES (%s, %s, NULL, %s, %s)
                    """,
                    (row["id"], ReservationPhase.STARTING.value, now, now),
                )
                self._conn.execute(
                    "UPDATE tasks SET state = %s, updated_at = %s WHERE id = %s",
                    (TaskState.STARTING.value, now, row["id"]),
                )
                claimed = self._conn.execute(
                    "SELECT * FROM tasks WHERE id = %s", (row["id"],)
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
                "SELECT * FROM task_reservations WHERE task_id = %s", (task_id,)
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
            self._begin_write()
            try:
                now = _utcnow_iso()
                updated = self._conn.execute(
                    """
                    UPDATE task_reservations
                    SET phase = %s, condition = %s, updated_at = %s
                    WHERE task_id = %s
                    """,
                    (phase.value, condition, now, task_id),
                )
                if updated.rowcount != 1:
                    raise KeyError(f"no reservation for task {task_id}")
                if task_state is not None and not self._task_state_is_terminal(task_id):
                    self._conn.execute(
                        "UPDATE tasks SET state = %s, updated_at = %s WHERE id = %s",
                        (task_state.value, now, task_id),
                    )
                row = self._conn.execute(
                    "SELECT * FROM task_reservations WHERE task_id = %s", (task_id,)
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
            self._begin_write()
            try:
                now = _utcnow_iso()
                self._conn.execute(
                    "DELETE FROM task_reservations WHERE task_id = %s", (task_id,)
                )
                self._conn.execute(
                    """
                    UPDATE tasks
                    SET sandbox_cleanup_status = %s, updated_at = %s
                    WHERE id = %s
                    """,
                    (cleanup_status, now, task_id),
                )
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

    def mark_sandbox_lost(self, task_id: str, *, detail: str) -> None:
        """Fail execution without erasing previously captured task evidence.

        A task that already settled successfully stays completed. The sandbox
        exiting after publication is cleanup, not a new failure.
        """

        assert self._conn is not None
        with self._lock:
            self._begin_write()
            try:
                now = _utcnow_iso()
                row = self._conn.execute(
                    "SELECT state, outcome_detail FROM tasks WHERE id = %s",
                    (task_id,),
                ).fetchone()
                if row is None:
                    self._conn.execute("COMMIT")
                    return
                current = TaskState(row["state"])
                outcome = row["outcome_detail"]
                if current is TaskState.CANCELLED:
                    next_state = TaskState.CANCELLED
                elif (
                    current is TaskState.COMPLETED
                    or outcome in _SETTLED_SUCCESS_OUTCOMES
                ):
                    next_state = TaskState.COMPLETED
                else:
                    next_state = TaskState.FAILED
                self._conn.execute(
                    """
                    UPDATE tasks
                    SET state = %s, outcome_detail = COALESCE(outcome_detail, %s),
                        sandbox_cleanup_status = %s, updated_at = %s
                    WHERE id = %s
                    """,
                    (
                        next_state.value,
                        detail,
                        "confirmed_absent",
                        now,
                        task_id,
                    ),
                )
                self._conn.execute(
                    "DELETE FROM task_reservations WHERE task_id = %s", (task_id,)
                )
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

    def settle_successful_tasks(self) -> None:
        """Complete tasks whose work already settled and whose sandbox is gone."""

        assert self._conn is not None
        with self._lock:
            self._begin_write()
            try:
                now = _utcnow_iso()
                placeholders = ",".join("%s" for _ in _SETTLED_SUCCESS_OUTCOMES)
                self._conn.execute(
                    f"""
                    UPDATE tasks
                    SET state = %s, updated_at = %s
                    WHERE sandbox_cleanup_status = 'confirmed_absent'
                      AND outcome_detail IN ({placeholders})
                      AND state NOT IN (%s, %s)
                    """,
                    (
                        TaskState.COMPLETED.value,
                        now,
                        *_SETTLED_SUCCESS_OUTCOMES,
                        TaskState.COMPLETED.value,
                        TaskState.CANCELLED.value,
                    ),
                )
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

    def _task_state_is_terminal(self, task_id: str) -> bool:
        assert self._conn is not None
        row = self._conn.execute(
            "SELECT state FROM tasks WHERE id = %s", (task_id,)
        ).fetchone()
        if row is None:
            return False
        return TaskState(row["state"]) in _TERMINAL_TASK_STATES

    def begin_sandbox_creation(
        self,
        *,
        task_id: str,
        deployment: str,
        sandbox_name: str,
        tags_json: str,
        session_api_key: str,
        credential_version: int | None = None,
    ) -> tuple[SandboxCreationRecord, bool]:
        """Persist creation intent before any provider call."""

        assert self._conn is not None
        with self._lock:
            self._begin_write()
            try:
                existing = self._conn.execute(
                    "SELECT * FROM sandbox_creations WHERE task_id = %s", (task_id,)
                ).fetchone()
                if existing is not None:
                    self._conn.execute("COMMIT")
                    return _row_to_sandbox_record(existing), False
                now = _utcnow_iso()
                self._conn.execute(
                    """
                    INSERT INTO sandbox_creations (
                        task_id, deployment, sandbox_name, tags_json,
                        session_api_key, credential_version, provider_id,
                        provider_state, detail,
                        created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, NULL, %s, NULL, %s, %s)
                    """,
                    (
                        task_id,
                        deployment,
                        sandbox_name,
                        tags_json,
                        session_api_key,
                        credential_version,
                        SandboxProviderState.CREATING.value,
                        now,
                        now,
                    ),
                )
                row = self._conn.execute(
                    "SELECT * FROM sandbox_creations WHERE task_id = %s", (task_id,)
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
                "SELECT * FROM sandbox_creations WHERE task_id = %s", (task_id,)
            ).fetchone()
        return _row_to_sandbox_record(row) if row is not None else None

    def set_sandbox_credential_version(
        self, task_id: str, version: int | None
    ) -> SandboxCreationRecord:
        """Record the newly resolved version before retrying an absent provider."""
        assert self._conn is not None
        with self._lock:
            row = self._conn.execute(
                "UPDATE sandbox_creations SET credential_version = %s "
                "WHERE task_id = %s RETURNING *",
                (version, task_id),
            ).fetchone()
        if row is None:
            raise KeyError(task_id)
        return _row_to_sandbox_record(row)

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
                    SET provider_state = %s, detail = %s, updated_at = %s
                    WHERE task_id = %s
                    """,
                    (provider_state.value, detail, now, task_id),
                )
            else:
                self._conn.execute(
                    """
                    UPDATE sandbox_creations
                    SET provider_id = %s, provider_state = %s,
                        detail = %s, updated_at = %s
                    WHERE task_id = %s
                    """,
                    (provider_id, provider_state.value, detail, now, task_id),
                )
            row = self._conn.execute(
                "SELECT * FROM sandbox_creations WHERE task_id = %s", (task_id,)
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
            self._begin_write()
            try:
                existing = self._conn.execute(
                    "SELECT * FROM publication_intents WHERE task_id = %s",
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
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        NULL, NULL, NULL, NULL, NULL, %s, %s, %s
                    )
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
                    "SELECT * FROM publication_intents WHERE task_id = %s",
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
                "SELECT * FROM publication_intents WHERE task_id = %s",
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
        check_outcome: CheckOutcome | None = None,
        agent_outcome: AgentOutcome | None = None,
    ) -> PublicationRecord:
        """Record publication progress without storing credentials."""

        assert self._conn is not None
        with self._lock:
            self._begin_write()
            try:
                now = _utcnow_iso()
                current = self._conn.execute(
                    "SELECT * FROM publication_intents WHERE task_id = %s",
                    (task_id,),
                ).fetchone()
                if current is None:
                    raise KeyError(f"no publication intent for task {task_id}")
                draft_value = current["pr_draft"] if pr_draft is None else int(pr_draft)
                self._conn.execute(
                    """
                    UPDATE publication_intents
                    SET state = %s,
                        commit_sha = COALESCE(%s, commit_sha),
                        pr_number = COALESCE(%s, pr_number),
                        pr_url = COALESCE(%s, pr_url),
                        pr_draft = %s,
                        pr_author = COALESCE(%s, pr_author),
                        pr_state = COALESCE(%s, pr_state),
                        detail = %s,
                        check_outcome = COALESCE(%s, check_outcome),
                        agent_outcome = COALESCE(%s, agent_outcome),
                        updated_at = %s
                    WHERE task_id = %s
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
                        None if check_outcome is None else check_outcome.value,
                        None if agent_outcome is None else agent_outcome.value,
                        now,
                        task_id,
                    ),
                )
                if check_status is not None or outcome_detail is not None:
                    self._conn.execute(
                        """
                        UPDATE tasks
                        SET check_status = COALESCE(%s, check_status),
                            outcome_detail = COALESCE(%s, outcome_detail),
                            updated_at = %s
                        WHERE id = %s
                        """,
                        (check_status, outcome_detail, now, task_id),
                    )
                row = self._conn.execute(
                    "SELECT * FROM publication_intents WHERE task_id = %s",
                    (task_id,),
                ).fetchone()
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
        assert row is not None
        return _row_to_publication(row)

    def begin_supervision(
        self,
        *,
        task_id: str,
        execution_id: str,
        task_branch: str,
        start_key: str,
        conversation_id: str | None = None,
    ) -> tuple[SupervisionRecord, bool]:
        """Persist execution identity before nonblocking sandbox startup."""

        assert self._conn is not None
        with self._lock:
            self._begin_write()
            try:
                existing = self._conn.execute(
                    """
                    SELECT * FROM task_supervisions
                    WHERE task_id = %s OR start_key = %s
                    """,
                    (task_id, start_key),
                ).fetchone()
                if existing is not None:
                    record = _row_to_supervision(existing)
                    if record.task_id != task_id or record.start_key != start_key:
                        self._conn.execute("ROLLBACK")
                        raise SupervisionIdentityError(
                            "start_key already bound to a different task"
                        )
                    self._conn.execute("COMMIT")
                    return record, False
                now = _utcnow_iso()
                self._conn.execute(
                    """
                    INSERT INTO task_supervisions (
                        task_id, execution_id, task_branch, start_key,
                        conversation_id, cancel_requested, tail_gap_possible,
                        created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, 0, 0, %s, %s)
                    """,
                    (
                        task_id,
                        execution_id,
                        task_branch,
                        start_key,
                        conversation_id,
                        now,
                        now,
                    ),
                )
                row = self._conn.execute(
                    "SELECT * FROM task_supervisions WHERE task_id = %s", (task_id,)
                ).fetchone()
                self._conn.execute("COMMIT")
            except SupervisionIdentityError:
                raise
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
        assert row is not None
        return _row_to_supervision(row), True

    def get_supervision(self, task_id: str) -> SupervisionRecord | None:
        assert self._conn is not None
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM task_supervisions WHERE task_id = %s", (task_id,)
            ).fetchone()
        return _row_to_supervision(row) if row is not None else None

    def update_supervision(
        self,
        task_id: str,
        *,
        execution_id: str | None = None,
        start_key: str | None = None,
        conversation_id: str | None = None,
        cancel_requested: bool | None = None,
        tail_gap_possible: bool | None = None,
    ) -> SupervisionRecord:
        assert self._conn is not None
        with self._lock:
            now = _utcnow_iso()
            current = self._conn.execute(
                "SELECT * FROM task_supervisions WHERE task_id = %s", (task_id,)
            ).fetchone()
            if current is None:
                raise KeyError(f"no supervision record for task {task_id}")
            execution = execution_id or current["execution_id"]
            key = start_key or current["start_key"]
            conversation = (
                current["conversation_id"]
                if conversation_id is None
                else conversation_id
            )
            cancel = (
                bool(current["cancel_requested"])
                if cancel_requested is None
                else cancel_requested
            )
            tail = (
                bool(current["tail_gap_possible"])
                if tail_gap_possible is None
                else tail_gap_possible
            )
            self._conn.execute(
                """
                UPDATE task_supervisions
                SET execution_id = %s, start_key = %s, conversation_id = %s,
                    cancel_requested = %s, tail_gap_possible = %s, updated_at = %s
                WHERE task_id = %s
                """,
                (execution, key, conversation, int(cancel), int(tail), now, task_id),
            )
            row = self._conn.execute(
                "SELECT * FROM task_supervisions WHERE task_id = %s", (task_id,)
            ).fetchone()
        assert row is not None
        return _row_to_supervision(row)

    def copy_task_event(
        self,
        *,
        task_id: str,
        source_id: str,
        source_seq: int,
        event: Event,
        event_json: str | None = None,
    ) -> int | None:
        """Insert one copied event; return cursor or None when deduplicated."""

        assert self._conn is not None
        payload = event_json if event_json is not None else event.model_dump_json()
        with self._lock:
            self._begin_write()
            try:
                existing = self._conn.execute(
                    """
                    SELECT cursor_seq FROM task_event_copies
                    WHERE task_id = %s AND source_id = %s AND source_seq = %s
                    """,
                    (task_id, source_id, source_seq),
                ).fetchone()
                if existing is not None:
                    self._conn.execute("COMMIT")
                    return None
                next_row = self._conn.execute(
                    """
                    SELECT COALESCE(MAX(cursor_seq), 0) + 1 AS next_cursor
                    FROM task_event_copies WHERE task_id = %s
                    """,
                    (task_id,),
                ).fetchone()
                cursor = int(next_row["next_cursor"])
                now = _utcnow_iso()
                self._conn.execute(
                    """
                    INSERT INTO task_event_copies (
                        task_id, cursor_seq, source_id, source_seq,
                        event_json, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        task_id,
                        cursor,
                        source_id,
                        source_seq,
                        payload,
                        now,
                    ),
                )
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
        return cursor

    def list_task_events(
        self, task_id: str, *, after_cursor: int = 0
    ) -> list[tuple[int, str, int, Event]]:
        assert self._conn is not None
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT cursor_seq, source_id, source_seq, event_json
                FROM task_event_copies
                WHERE task_id = %s AND cursor_seq > %s
                ORDER BY cursor_seq ASC
                """,
                (task_id, after_cursor),
            ).fetchall()
        copied: list[tuple[int, str, int, Event]] = []
        for row in rows:
            copied.append(
                (
                    int(row["cursor_seq"]),
                    row["source_id"],
                    int(row["source_seq"]),
                    Event.model_validate_json(row["event_json"]),
                )
            )
        return copied

    def save_task_message_receipt(self, task_id: str, receipt: MessageReceipt) -> None:
        assert self._conn is not None
        with self._lock:
            self._begin_write()
            try:
                saved = self._conn.execute(
                    """
                    INSERT INTO task_message_receipts (
                        task_id, message_id, content, status, detail,
                        created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT(task_id, message_id) DO UPDATE SET
                        content = excluded.content,
                        status = excluded.status,
                        detail = excluded.detail,
                        updated_at = excluded.updated_at
                    WHERE task_message_receipts.content = excluded.content
                    """,
                    (
                        task_id,
                        receipt.id,
                        receipt.content,
                        receipt.status.value,
                        receipt.detail,
                        receipt.created_at.isoformat(),
                        receipt.updated_at.isoformat(),
                    ),
                )
                if saved.rowcount != 1:
                    raise RuntimeError("message id already belongs to another message")
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

    def get_task_message_receipt(
        self, task_id: str, message_id: str
    ) -> MessageReceipt | None:
        assert self._conn is not None
        with self._lock:
            row = self._conn.execute(
                """
                SELECT * FROM task_message_receipts
                WHERE task_id = %s AND message_id = %s
                """,
                (task_id, message_id),
            ).fetchone()
        return _row_to_message_receipt(row) if row is not None else None

    def list_task_message_receipts(self, task_id: str) -> list[MessageReceipt]:
        assert self._conn is not None
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT * FROM task_message_receipts
                WHERE task_id = %s ORDER BY created_at, message_id
                """,
                (task_id,),
            ).fetchall()
        return [_row_to_message_receipt(row) for row in rows]

    def list_accepted_task_messages(self, task_id: str) -> list[MessageReceipt]:
        receipts = self.list_task_message_receipts(task_id)
        return [
            item for item in receipts if item.status is MessageDeliveryStatus.ACCEPTED
        ]

    def archive_task_result(
        self,
        *,
        task_id: str,
        execution_id: str | None,
        manifest: TaskResultManifest | None,
        evidence_complete: bool,
        evidence_detail: str | None,
    ) -> TaskResultArchive:
        assert self._conn is not None
        with self._lock:
            self._begin_write()
            try:
                now = _utcnow_iso()
                manifest_json = None if manifest is None else manifest.model_dump_json()
                self._conn.execute(
                    """
                    INSERT INTO task_results (
                        task_id, execution_id, manifest_json,
                        evidence_complete, evidence_detail, archived_at
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT(task_id) DO UPDATE SET
                        execution_id = excluded.execution_id,
                        manifest_json = excluded.manifest_json,
                        evidence_complete = excluded.evidence_complete,
                        evidence_detail = excluded.evidence_detail,
                        archived_at = excluded.archived_at
                    """,
                    (
                        task_id,
                        execution_id,
                        manifest_json,
                        int(evidence_complete),
                        evidence_detail,
                        now,
                    ),
                )
                row = self._conn.execute(
                    "SELECT * FROM task_results WHERE task_id = %s", (task_id,)
                ).fetchone()
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
        assert row is not None
        return _row_to_task_result(row)

    def get_task_result(self, task_id: str) -> TaskResultArchive | None:
        assert self._conn is not None
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM task_results WHERE task_id = %s", (task_id,)
            ).fetchone()
        return _row_to_task_result(row) if row is not None else None

    def cancel_queued_task(self, task_id: str) -> TaskRecord | None:
        """Cancel a queued task before sandbox allocation."""

        assert self._conn is not None
        with self._lock:
            self._begin_write()
            try:
                row = self._conn.execute(
                    "SELECT * FROM tasks WHERE id = %s", (task_id,)
                ).fetchone()
                if row is None:
                    self._conn.execute("COMMIT")
                    return None
                if TaskState(row["state"]) is not TaskState.QUEUED:
                    self._conn.execute("COMMIT")
                    return _row_to_record(row)
                now = _utcnow_iso()
                self._conn.execute(
                    """
                    UPDATE tasks
                    SET state = %s, outcome_detail = %s, updated_at = %s
                    WHERE id = %s
                    """,
                    (
                        TaskState.CANCELLED.value,
                        "cancelled_before_allocation",
                        now,
                        task_id,
                    ),
                )
                updated = self._conn.execute(
                    "SELECT * FROM tasks WHERE id = %s", (task_id,)
                ).fetchone()
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
        assert updated is not None
        return _row_to_record(updated)

    def request_task_cancel(self, task_id: str) -> SupervisionRecord | None:
        """Mark a running task for cooperative cancellation."""

        supervision = self.get_supervision(task_id)
        if supervision is None:
            return None
        return self.update_supervision(task_id, cancel_requested=True)

    def finish_task(
        self,
        task_id: str,
        *,
        state: TaskState,
        outcome_detail: str | None = None,
        check_status: str | None = None,
    ) -> TaskRecord:
        assert self._conn is not None
        with self._lock:
            self._begin_write()
            try:
                now = _utcnow_iso()
                self._conn.execute(
                    """
                    UPDATE tasks
                    SET state = %s,
                        outcome_detail = COALESCE(%s, outcome_detail),
                        check_status = COALESCE(%s, check_status),
                        updated_at = %s,
                        workspace_last_activity_at = CASE WHEN %s = %s
                            THEN workspace_last_activity_at ELSE %s END
                    WHERE id = %s
                    """,
                    (
                        state.value,
                        outcome_detail,
                        check_status,
                        now,
                        state.value,
                        TaskState.SLEEPING.value,
                        now,
                        task_id,
                    ),
                )
                row = self._conn.execute(
                    "SELECT * FROM tasks WHERE id = %s", (task_id,)
                ).fetchone()
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
        if row is None:
            raise KeyError(f"no task {task_id}")
        return _row_to_record(row)

    def queue_workspace_message(self, task_id: str) -> None:
        """Wake a sleeping workspace after its message receipt is durable."""
        assert self._conn is not None
        with self._lock:
            self._conn.execute(
                "UPDATE tasks SET state = %s, updated_at = %s "
                "WHERE id = %s AND state = %s",
                (
                    TaskState.QUEUED.value,
                    _utcnow_iso(),
                    task_id,
                    TaskState.SLEEPING.value,
                ),
            )

    def touch_workspace(self, task_id: str) -> None:
        assert self._conn is not None
        with self._lock:
            self._conn.execute(
                "UPDATE tasks SET updated_at = %s, workspace_last_activity_at = %s "
                "WHERE id = %s",
                (_utcnow_iso(), _utcnow_iso(), task_id),
            )

    def try_mark_sleeping(self, task_id: str) -> bool:
        """Close the idle window atomically with the message queue."""
        assert self._conn is not None
        with self._lock:
            self._begin_write()
            try:
                pending = self._conn.execute(
                    "SELECT 1 FROM task_message_receipts WHERE task_id = %s "
                    "AND status = %s LIMIT 1",
                    (task_id, MessageDeliveryStatus.ACCEPTED.value),
                ).fetchone()
                if pending is not None:
                    self._conn.execute("COMMIT")
                    return False
                updated = self._conn.execute(
                    "UPDATE tasks SET state = %s, updated_at = %s "
                    "WHERE id = %s AND state = %s",
                    (
                        TaskState.SLEEPING.value,
                        _utcnow_iso(),
                        task_id,
                        TaskState.IDLE.value,
                    ),
                )
                self._conn.execute("COMMIT")
                return updated.rowcount == 1
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

    def expire_workspace(self, task_id: str) -> None:
        assert self._conn is not None
        with self._lock:
            self._conn.execute(
                "UPDATE tasks SET workspace_expired = 1 WHERE id = %s AND state = %s",
                (task_id, TaskState.SLEEPING.value),
            )

    def reset_sandbox_for_wake(self, task_id: str) -> None:
        """Discard the old provider identity after absence was confirmed."""
        assert self._conn is not None
        with self._lock:
            self._conn.execute(
                "UPDATE sandbox_creations SET provider_id = NULL, "
                "provider_state = %s, detail = NULL, updated_at = %s "
                "WHERE task_id = %s AND provider_state = %s",
                (
                    SandboxProviderState.CREATING.value,
                    _utcnow_iso(),
                    task_id,
                    SandboxProviderState.STOPPED.value,
                ),
            )

    def _schema_version(self) -> int:
        assert self._conn is not None
        row = self._conn.execute(
            "SELECT value FROM schema_meta WHERE key = 'schema_version'"
        ).fetchone()
        return int(row["value"]) if row is not None else 0

    def ping_database(self) -> bool:
        try:
            assert self._conn is not None
            with self._lock:
                self._conn.execute("SELECT 1")
        except (psycopg.Error, AssertionError):
            return False
        return True

    def count_task_log_bytes(self, task_id: str) -> int:
        assert self._conn is not None
        with self._lock:
            row = self._conn.execute(
                """
                SELECT
                    COALESCE((
                        SELECT SUM(LENGTH(event_json))
                        FROM task_event_copies WHERE task_id = %s
                    ), 0)
                    + COALESCE((
                        SELECT SUM(LENGTH(content) + LENGTH(COALESCE(detail, '')))
                        FROM task_message_receipts WHERE task_id = %s
                    ), 0) AS total
                """,
                (task_id, task_id),
            ).fetchone()
        return int(row["total"])

    def count_task_artifact_bytes(self, task_id: str) -> int:
        assert self._conn is not None
        with self._lock:
            row = self._conn.execute(
                """
                SELECT COALESCE(LENGTH(manifest_json), 0) AS total
                FROM task_results WHERE task_id = %s
                """,
                (task_id,),
            ).fetchone()
        return int(row["total"]) if row is not None else 0

    def count_total_evidence_bytes(self) -> int:
        assert self._conn is not None
        with self._lock:
            row = self._conn.execute(
                """
                SELECT
                    COALESCE((SELECT SUM(LENGTH(event_json)) FROM task_event_copies), 0)
                    + COALESCE((
                        SELECT SUM(LENGTH(content) + LENGTH(COALESCE(detail, '')))
                        FROM task_message_receipts
                    ), 0)
                    + COALESCE((
                        SELECT SUM(LENGTH(manifest_json)) FROM task_results
                    ), 0) AS total
                """
            ).fetchone()
        return int(row["total"])

    def protected_task_ids(self) -> set[str]:
        return {item.task_id for item in self.list_reservations()}

    def expire_terminal_payloads(
        self,
        *,
        before: datetime,
        tombstone_retention: timedelta,
    ) -> int:
        """Drop bulky evidence for terminal tasks while keeping dedupe metadata."""

        assert self._conn is not None
        terminal = (
            TaskState.COMPLETED.value,
            TaskState.FAILED.value,
            TaskState.CANCELLED.value,
        )
        protected = self.protected_task_ids()
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT * FROM tasks
                WHERE state IN (%s, %s, %s)
                  AND payload_expired = 0
                  AND updated_at < %s
                ORDER BY updated_at ASC
                """,
                (*terminal, before.isoformat()),
            ).fetchall()
        expired = 0
        for row in rows:
            task_id = row["id"]
            if task_id in protected:
                continue
            self._expire_task_payload(
                task_id,
                record=row,
                tombstone_retention=tombstone_retention,
            )
            expired += 1
        return expired

    def purge_expired_tombstones(self, *, before: datetime) -> int:
        assert self._conn is not None
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT task_id FROM retention_tombstones
                WHERE expires_at < %s
                """,
                (before.isoformat(),),
            ).fetchall()
            for row in rows:
                self._conn.execute(
                    "DELETE FROM retention_tombstones WHERE task_id = %s",
                    (row["task_id"],),
                )
        return len(rows)

    def _expire_task_payload(
        self,
        task_id: str,
        *,
        record: dict[str, Any],
        tombstone_retention: timedelta,
    ) -> None:
        assert self._conn is not None
        now = _utcnow_iso()
        with self._lock:
            publication_row = self._conn.execute(
                "SELECT * FROM publication_intents WHERE task_id = %s",
                (task_id,),
            ).fetchone()
        remote_effect = None
        if publication_row is not None:
            publication = _row_to_publication(publication_row)
            remote_effect = json.dumps(
                {
                    "pr_number": publication.pr_number,
                    "pr_url": publication.pr_url,
                    "pr_state": publication.pr_state,
                    "state": publication.state.value,
                },
                separators=(",", ":"),
            )
        expires_at = (datetime.fromisoformat(now) + tombstone_retention).isoformat()
        with self._lock:
            self._begin_write()
            try:
                self._conn.execute(
                    """
                    INSERT INTO retention_tombstones (
                        idempotency_key, owner_id, task_id, repository, prompt,
                        base_ref, retry_of, model, terminal_state, seq,
                        created_at, updated_at,
                        remote_effect_json, payload_expired_at, expires_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s
                    )
                    ON CONFLICT(task_id) DO UPDATE SET
                        remote_effect_json = excluded.remote_effect_json,
                        payload_expired_at = excluded.payload_expired_at,
                        expires_at = excluded.expires_at
                    """,
                    (
                        record["idempotency_key"],
                        record["owner_id"],
                        task_id,
                        record["repository"],
                        record["prompt"],
                        record["base_ref"],
                        record["retry_of"],
                        record["model"],
                        record["state"],
                        record["seq"],
                        record["created_at"],
                        record["updated_at"],
                        remote_effect,
                        now,
                        expires_at,
                    ),
                )
                self._conn.execute(
                    "DELETE FROM task_event_copies WHERE task_id = %s", (task_id,)
                )
                self._conn.execute(
                    "DELETE FROM task_message_receipts WHERE task_id = %s",
                    (task_id,),
                )
                self._conn.execute(
                    """
                    UPDATE task_results
                    SET manifest_json = NULL,
                        evidence_complete = 0,
                        evidence_detail = 'payload expired by retention policy'
                    WHERE task_id = %s
                    """,
                    (task_id,),
                )
                self._conn.execute(
                    """
                    UPDATE tasks SET payload_expired = 1, updated_at = %s
                    WHERE id = %s
                    """,
                    (now, task_id),
                )
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

    @staticmethod
    def _record_from_tombstone(row: dict[str, Any]) -> TaskRecord:
        return TaskRecord(
            owner_id=row["owner_id"],
            id=row["task_id"],
            seq=row["seq"],
            state=TaskState(row["terminal_state"]),
            idempotency_key=row["idempotency_key"],
            repository=row["repository"] or None,
            prompt=row["prompt"],
            base_ref=row["base_ref"],
            retry_of=row["retry_of"],
            model=row["model"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            payload_expired=True,
        )


def _row_to_supervision(row: dict[str, Any]) -> SupervisionRecord:
    return SupervisionRecord(
        task_id=row["task_id"],
        execution_id=row["execution_id"],
        task_branch=row["task_branch"],
        start_key=row["start_key"],
        conversation_id=row["conversation_id"],
        cancel_requested=bool(row["cancel_requested"]),
        tail_gap_possible=bool(row["tail_gap_possible"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _row_to_message_receipt(row: dict[str, Any]) -> MessageReceipt:
    return MessageReceipt(
        id=row["message_id"],
        content=row["content"],
        status=MessageDeliveryStatus(row["status"]),
        detail=row["detail"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _row_to_task_result(row: dict[str, Any]) -> TaskResultArchive:
    manifest = (
        None
        if row["manifest_json"] is None
        else TaskResultManifest.model_validate_json(row["manifest_json"])
    )
    archived_at = (
        None
        if row["archived_at"] is None
        else datetime.fromisoformat(row["archived_at"])
    )
    return TaskResultArchive(
        task_id=row["task_id"],
        execution_id=row["execution_id"],
        manifest=manifest,
        evidence_complete=bool(row["evidence_complete"]),
        evidence_detail=row["evidence_detail"],
        archived_at=archived_at,
    )


class SupervisionIdentityError(RuntimeError):
    """Supervision identity does not match the requested task."""


class PublicationIdentityError(RuntimeError):
    """A task's stored publication identity does not match a retry."""


__all__ = [
    "SUPPORTED_SCHEMA_VERSION",
    "PublicationIdentityError",
    "ReservationPhase",
    "ReservationRecord",
    "SandboxCreationRecord",
    "SandboxProviderState",
    "SupervisionIdentityError",
    "SupervisionRecord",
    "TaskLedger",
    "TaskResultArchive",
]
