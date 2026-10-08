"""SQLite task ledger; all writes join the shared runtime revision."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from gg.runtime.checkpoints import CheckpointCoordinator
from gg.runtime.local_sessions import durable
from gg.runtime.sqlite_db import SQLiteDB
from gg.runtime.sqlite_migrations import SCHEMA_VERSION
from gg.sdk.agent_backend import DEFAULT_PI_MODEL
from gg.sdk.domain import Event, MessageDeliveryStatus, MessageReceipt
from gg.sdk.publication import PublicationRecord, PublicationState
from gg.sdk.task_execution import AgentOutcome, CheckOutcome, TaskResultManifest
from gg.sdk.tasks import TaskRecord, TaskState


SUPPORTED_SCHEMA_VERSION = SCHEMA_VERSION

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
        agent_outcome=row.get("agent_outcome"),
        check_status=row["check_status"],
        sandbox_cleanup_status=row["sandbox_cleanup_status"],
        payload_expired=bool(row["payload_expired"])
        if "payload_expired" in row.keys()
        else False,
        workspace_expired=bool(row["workspace_expired"])
        if "workspace_expired" in row.keys()
        else False,
        workspace_last_activity_at=datetime.fromisoformat(
            row["workspace_last_activity_at"]
        )
        if "workspace_last_activity_at" in row.keys()
        and row["workspace_last_activity_at"]
        else None,
    )


class TaskLedger:
    """Native SQL port of task operations, borrowing one shared database."""

    def __init__(
        self, database: SQLiteDB, checkpoints: CheckpointCoordinator | None = None
    ):
        if checkpoints is not None and checkpoints.db is not database:
            raise ValueError("ledger and checkpoints must share a database")
        self._database = database
        self.checkpoints = checkpoints

    @property
    def db(self) -> SQLiteDB:
        return self._database

    async def ensure_durable(self):
        if self.checkpoints is not None:
            await durable(self.checkpoints, self.db.revision)

    def open(self):
        # The caller owns the database lifecycle; verify existing state only.
        self.db.revision

    def close(self):
        self.db.close()

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *_):
        self.close()

    @contextmanager
    def _read_connection(self) -> Iterator[sqlite3.Connection]:
        with self._database.read() as connection:
            connection.row_factory = lambda cursor, values: dict(
                zip((c[0] for c in cursor.description), values)
            )
            yield connection

    @contextmanager
    def _write_connection(self) -> Iterator[sqlite3.Connection]:
        with self._database.write() as transaction:
            transaction.connection.row_factory = lambda cursor, values: dict(
                zip((c[0] for c in cursor.description), values)
            )
            try:
                yield transaction.connection
            finally:
                transaction.connection.row_factory = None

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
        with self._write_connection() as connection:
            scope, scope_params = self._owner_scope(owner_id)
            existing = connection.execute(
                f"SELECT * FROM tasks WHERE idempotency_key = ? AND {scope}",
                (idempotency_key, *scope_params),
            ).fetchone()
            if existing is not None:
                return (_row_to_record(existing), False)
            retired = connection.execute(
                f"SELECT * FROM task_idempotency WHERE idempotency_key = ? AND {scope}",
                (idempotency_key, *scope_params),
            ).fetchone()
            if retired is not None:
                return (self._record_from_tombstone(retired), False)
            seq_row = connection.execute(
                """
            UPDATE ledger_counters SET value = value + 1 WHERE name = ?
            RETURNING value AS next_seq
            """,
                ("task_seq",),
            ).fetchone()
            seq = int(seq_row["next_seq"])
            now = _utcnow_iso()
            task_id = str(uuid4())
            connection.execute(
                """
            INSERT INTO tasks ( id, seq, state, idempotency_key, owner_id,
            repository, prompt, base_ref, base_sha, retry_of, model, created_at,
            updated_at, outcome_detail, check_status, sandbox_cleanup_status )
            VALUES ( ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, NULL, NULL, NULL
            )
            """,
                (
                    task_id,
                    seq,
                    TaskState.QUEUED.value,
                    idempotency_key,
                    None if owner_id is None else str(owner_id),
                    repository or "",
                    prompt,
                    base_ref,
                    retry_of,
                    model,
                    now,
                    now,
                ),
            )
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

    def record_base_sha(self, task_id: str, base_sha: str) -> TaskRecord:
        """Persist the resolved starting revision for one task."""
        with self._write_connection() as connection:
            now = _utcnow_iso()
            updated = connection.execute(
                "UPDATE tasks SET base_sha = ?, updated_at = ? WHERE id = ?",
                (base_sha, now, task_id),
            )
            if updated.rowcount != 1:
                raise KeyError(f"no task {task_id}")
            row = connection.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
        assert row is not None
        return _row_to_record(row)

    @staticmethod
    def _owner_scope(owner_id: UUID | None) -> tuple[str, tuple[str, ...]]:
        if owner_id is None:
            return ("owner_id IS NULL", ())
        return ("owner_id = ?", (str(owner_id),))

    def get(self, task_id: str, *, owner_id: UUID | None = None) -> TaskRecord | None:
        with self._read_connection() as connection:
            query = """
            SELECT tasks.*, json_extract(results.manifest_json,
            '$.agent_outcome') AS agent_outcome FROM tasks LEFT JOIN
            task_results AS results ON results.task_id = tasks.id
            WHERE tasks.id = ?
            """
            if owner_id is None:
                row = connection.execute(query, (task_id,)).fetchone()
            else:
                row = connection.execute(
                    query + "AND tasks.owner_id = ?", (task_id, str(owner_id))
                ).fetchone()
        return _row_to_record(row) if row is not None else None

    def list(self, *, owner_id: UUID | None = None) -> list[TaskRecord]:
        with self._read_connection() as connection:
            query = """
            SELECT tasks.*, json_extract(results.manifest_json,
            '$.agent_outcome') AS agent_outcome FROM tasks LEFT JOIN
            task_results AS results ON results.task_id = tasks.id
            """
            if owner_id is None:
                rows = connection.execute(query + "ORDER BY tasks.seq ASC").fetchall()
            else:
                rows = connection.execute(
                    query + "WHERE tasks.owner_id = ? ORDER BY tasks.seq ASC",
                    (str(owner_id),),
                ).fetchall()
        return [_row_to_record(row) for row in rows]

    def count_queued(self) -> int:
        with self._read_connection() as connection:
            return connection.execute(
                "SELECT COUNT(*) AS count FROM tasks WHERE state = 'queued'"
            ).fetchone()["count"]

    def sleeping_workspace_candidates(
        self, *, before: datetime, after_seq: int = 0, limit: int = 200
    ) -> list[TaskRecord]:
        """Return only due workspaces, in bounded keyset pages."""
        if not 1 <= limit <= 200:
            raise ValueError("candidate limit must be between 1 and 200")
        with self._read_connection() as connection:
            rows = connection.execute(
                """SELECT * FROM tasks INDEXED BY tasks_sleeping_expiry
                   WHERE state = 'sleeping'
                   AND workspace_expired = 0
                   AND COALESCE(workspace_last_activity_at, updated_at) <= ?
                   AND seq > ? ORDER BY seq LIMIT ?""",
                (before.isoformat(), after_seq, limit),
            ).fetchall()
        return [_row_to_record(row) for row in rows]

    def reserve_next(self, *, capacity: int) -> TaskRecord | None:
        """Atomically reserve the oldest queued task if capacity is available."""
        if not 1 <= capacity <= 10:
            raise ValueError("reservation capacity must be between 1 and 10")
        with self._write_connection() as connection:
            active = int(
                connection.execute(
                    "SELECT COUNT(*) AS count FROM task_reservations"
                ).fetchone()["count"]
            )
            if active >= capacity:
                return None
            row = connection.execute(
                """
            SELECT tasks.* FROM tasks LEFT JOIN task_reservations ON
            task_reservations.task_id = tasks.id WHERE tasks.state = ? AND
            task_reservations.task_id IS NULL ORDER BY tasks.seq ASC LIMIT 1
            """,
                (TaskState.QUEUED.value,),
            ).fetchone()
            if row is None:
                return None
            now = _utcnow_iso()
            connection.execute(
                """
            INSERT INTO task_reservations ( task_id, phase, condition,
            reserved_at, updated_at ) VALUES (?, ?, NULL, ?, ?)
            """,
                (row["id"], ReservationPhase.STARTING.value, now, now),
            )
            connection.execute(
                "UPDATE tasks SET state = ?, updated_at = ? WHERE id = ?",
                (TaskState.STARTING.value, now, row["id"]),
            )
            claimed = connection.execute(
                "SELECT * FROM tasks WHERE id = ?", (row["id"],)
            ).fetchone()
        assert claimed is not None
        return _row_to_record(claimed)

    def list_reservations(self) -> list[ReservationRecord]:
        with self._read_connection() as connection:
            rows = connection.execute(
                "SELECT * FROM task_reservations ORDER BY reserved_at, task_id"
            ).fetchall()
        return [_row_to_reservation(row) for row in rows]

    def get_reservation(self, task_id: str) -> ReservationRecord | None:
        with self._read_connection() as connection:
            row = connection.execute(
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
        with self._write_connection() as connection:
            now = _utcnow_iso()
            updated = connection.execute(
                """
            UPDATE task_reservations SET phase = ?, condition = ?, updated_at =
            ? WHERE task_id = ?
            """,
                (phase.value, condition, now, task_id),
            )
            if updated.rowcount != 1:
                raise KeyError(f"no reservation for task {task_id}")
            if task_state is not None and (
                not self._task_state_is_terminal(connection, task_id)
            ):
                connection.execute(
                    "UPDATE tasks SET state = ?, updated_at = ? WHERE id = ?",
                    (task_state.value, now, task_id),
                )
            row = connection.execute(
                "SELECT * FROM task_reservations WHERE task_id = ?", (task_id,)
            ).fetchone()
        assert row is not None
        return _row_to_reservation(row)

    def release_reservation(
        self, task_id: str, *, cleanup_status: str = "confirmed_absent"
    ) -> None:
        """Release capacity only after provider absence has been confirmed."""
        with self._write_connection() as connection:
            now = _utcnow_iso()
            connection.execute(
                "DELETE FROM task_reservations WHERE task_id = ?", (task_id,)
            )
            connection.execute(
                """
            UPDATE tasks SET sandbox_cleanup_status = ?, updated_at = ? WHERE id
            = ?
            """,
                (cleanup_status, now, task_id),
            )

    def mark_sandbox_lost(self, task_id: str, *, detail: str) -> None:
        """Fail execution without erasing previously captured task evidence.

        A task that already settled successfully stays completed. The sandbox
        exiting after publication is cleanup, not a new failure.
        """
        with self._write_connection() as connection:
            now = _utcnow_iso()
            row = connection.execute(
                "SELECT state, outcome_detail FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
            if row is None:
                return
            current = TaskState(row["state"])
            outcome = row["outcome_detail"]
            if current is TaskState.CANCELLED:
                next_state = TaskState.CANCELLED
            elif current is TaskState.COMPLETED or outcome in _SETTLED_SUCCESS_OUTCOMES:
                next_state = TaskState.COMPLETED
            else:
                next_state = TaskState.FAILED
            connection.execute(
                """
            UPDATE tasks SET state = ?, outcome_detail =
            COALESCE(outcome_detail, ?), sandbox_cleanup_status = ?, updated_at
            = ? WHERE id = ?
            """,
                (next_state.value, detail, "confirmed_absent", now, task_id),
            )
            connection.execute(
                "DELETE FROM task_reservations WHERE task_id = ?", (task_id,)
            )

    def settle_successful_tasks(self) -> None:
        """Complete tasks whose work already settled and whose sandbox is gone."""
        with self._write_connection() as connection:
            now = _utcnow_iso()
            placeholders = ",".join("?" for _ in _SETTLED_SUCCESS_OUTCOMES)
            connection.execute(
                f"""UPDATE tasks SET state = ?, updated_at = ?
                    WHERE sandbox_cleanup_status = 'confirmed_absent'
                      AND outcome_detail IN ({placeholders})
                      AND state NOT IN ('completed', 'cancelled')""",
                (
                    TaskState.COMPLETED.value,
                    now,
                    *_SETTLED_SUCCESS_OUTCOMES,
                ),
            )

    def _task_state_is_terminal(
        self, connection: sqlite3.Connection, task_id: str
    ) -> bool:
        row = connection.execute(
            "SELECT state FROM tasks WHERE id = ?", (task_id,)
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
        with self._write_connection() as connection:
            self._require_payload(connection, task_id)
            existing = connection.execute(
                "SELECT * FROM sandbox_creations WHERE task_id = ?", (task_id,)
            ).fetchone()
            if existing is not None:
                if (
                    existing["deployment"],
                    existing["sandbox_name"],
                    existing["tags_json"],
                    existing["session_api_key"],
                ) != (deployment, sandbox_name, tags_json, session_api_key):
                    raise RuntimeError("sandbox creation identity does not match task")
                return (_row_to_sandbox_record(existing), False)
            now = _utcnow_iso()
            connection.execute(
                """
            INSERT INTO sandbox_creations ( task_id, deployment, sandbox_name,
            tags_json, session_api_key, credential_version, provider_id,
            provider_state, detail, created_at, updated_at ) VALUES (?, ?, ?, ?,
            ?, ?, NULL, ?, NULL, ?, ?)
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
            row = connection.execute(
                "SELECT * FROM sandbox_creations WHERE task_id = ?", (task_id,)
            ).fetchone()
        assert row is not None
        return (_row_to_sandbox_record(row), True)

    def get_sandbox_creation(self, task_id: str) -> SandboxCreationRecord | None:
        with self._read_connection() as connection:
            row = connection.execute(
                "SELECT * FROM sandbox_creations WHERE task_id = ?", (task_id,)
            ).fetchone()
        return _row_to_sandbox_record(row) if row is not None else None

    def set_sandbox_credential_version(
        self, task_id: str, version: int | None
    ) -> SandboxCreationRecord:
        """Record the newly resolved version before retrying an absent provider."""
        with self._write_connection() as connection:
            row = connection.execute(
                """
            UPDATE sandbox_creations SET credential_version = ? WHERE task_id =
            ? RETURNING *
            """,
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
        with self._write_connection() as connection:
            now = _utcnow_iso()
            if provider_id is None:
                connection.execute(
                    """
            UPDATE sandbox_creations SET provider_state = ?, detail = ?,
            updated_at = ? WHERE task_id = ?
            """,
                    (provider_state.value, detail, now, task_id),
                )
            else:
                connection.execute(
                    """
            UPDATE sandbox_creations SET provider_id = ?, provider_state = ?,
            detail = ?, updated_at = ? WHERE task_id = ?
            """,
                    (provider_id, provider_state.value, detail, now, task_id),
                )
            row = connection.execute(
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
        with self._write_connection() as connection:
            self._require_payload(connection, task_id)
            existing = connection.execute(
                "SELECT * FROM publication_intents WHERE task_id = ?", (task_id,)
            ).fetchone()
            if existing is not None:
                record = _row_to_publication(existing)
                if (
                    record.repository != repository
                    or record.task_branch != task_branch
                    or record.base_ref != base_ref
                    or (record.task_marker != task_marker)
                ):
                    raise PublicationIdentityError(
                        f"existing publication identity does not match task {task_id}"
                    )
                if (
                    record.commit_sha is not None
                    and commit_sha is not None
                    and (record.commit_sha != commit_sha)
                ):
                    raise PublicationIdentityError(
                        f"existing publication commit does not match task {task_id}"
                    )
                return (record, False)
            now = _utcnow_iso()
            connection.execute(
                """
            INSERT INTO publication_intents ( task_id, repository, task_branch,
            base_ref, task_marker, commit_sha, state, check_outcome,
            agent_outcome, pr_number, pr_url, pr_draft, pr_author, pr_state,
            detail, created_at, updated_at ) VALUES ( ?, ?, ?, ?, ?, ?, ?, ?, ?,
            NULL, NULL, NULL, NULL, NULL, ?, ?, ? )
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
            row = connection.execute(
                "SELECT * FROM publication_intents WHERE task_id = ?", (task_id,)
            ).fetchone()
        assert row is not None
        return (_row_to_publication(row), True)

    def get_publication(self, task_id: str) -> PublicationRecord | None:
        with self._read_connection() as connection:
            row = connection.execute(
                "SELECT * FROM publication_intents WHERE task_id = ?", (task_id,)
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
        with self._write_connection() as connection:
            now = _utcnow_iso()
            current = connection.execute(
                "SELECT * FROM publication_intents WHERE task_id = ?", (task_id,)
            ).fetchone()
            if current is None:
                raise KeyError(f"no publication intent for task {task_id}")
            draft_value = current["pr_draft"] if pr_draft is None else int(pr_draft)
            connection.execute(
                """
            UPDATE publication_intents SET state = ?, commit_sha = COALESCE(?,
            commit_sha), pr_number = COALESCE(?, pr_number), pr_url =
            COALESCE(?, pr_url), pr_draft = ?, pr_author = COALESCE(?,
            pr_author), pr_state = COALESCE(?, pr_state), detail = ?,
            check_outcome = COALESCE(?, check_outcome), agent_outcome =
            COALESCE(?, agent_outcome), updated_at = ? WHERE task_id = ?
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
                connection.execute(
                    """
            UPDATE tasks SET check_status = COALESCE(?, check_status),
            outcome_detail = COALESCE(?, outcome_detail), updated_at = ? WHERE
            id = ?
            """,
                    (check_status, outcome_detail, now, task_id),
                )
            row = connection.execute(
                "SELECT * FROM publication_intents WHERE task_id = ?", (task_id,)
            ).fetchone()
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
        with self._write_connection() as connection:
            self._require_payload(connection, task_id)
            existing = connection.execute(
                """
            SELECT * FROM task_supervisions WHERE task_id = ? OR start_key = ?
            """,
                (task_id, start_key),
            ).fetchone()
            if existing is not None:
                record = _row_to_supervision(existing)
                if (
                    record.task_id != task_id
                    or record.start_key != start_key
                    or record.execution_id != execution_id
                    or (record.task_branch != task_branch)
                ):
                    raise SupervisionIdentityError(
                        "start_key already bound to a different task"
                    )
                return (record, False)
            now = _utcnow_iso()
            connection.execute(
                """
            INSERT INTO task_supervisions ( task_id, execution_id, task_branch,
            start_key, conversation_id, cancel_requested, tail_gap_possible,
            created_at, updated_at ) VALUES (?, ?, ?, ?, ?, 0, 0, ?, ?)
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
            row = connection.execute(
                "SELECT * FROM task_supervisions WHERE task_id = ?", (task_id,)
            ).fetchone()
        assert row is not None
        return (_row_to_supervision(row), True)

    def get_supervision(self, task_id: str) -> SupervisionRecord | None:
        with self._read_connection() as connection:
            row = connection.execute(
                "SELECT * FROM task_supervisions WHERE task_id = ?", (task_id,)
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
        with self._write_connection() as connection:
            now = _utcnow_iso()
            current = connection.execute(
                "SELECT * FROM task_supervisions WHERE task_id = ?", (task_id,)
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
            connection.execute(
                """
            UPDATE task_supervisions SET execution_id = ?, start_key = ?,
            conversation_id = ?, cancel_requested = ?, tail_gap_possible = ?,
            updated_at = ? WHERE task_id = ?
            """,
                (execution, key, conversation, int(cancel), int(tail), now, task_id),
            )
            row = connection.execute(
                "SELECT * FROM task_supervisions WHERE task_id = ?", (task_id,)
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
        payload = event_json if event_json is not None else event.model_dump_json()
        with self._write_connection() as connection:
            existing = connection.execute(
                """
            SELECT cursor_seq FROM task_event_identities WHERE task_id = ? AND
            source_id = ? AND source_seq = ?
            """,
                (task_id, source_id, source_seq),
            ).fetchone()
            if existing is not None:
                return None
            self._require_payload(connection, task_id)
            connection.execute(
                """
            INSERT INTO task_event_counters(task_id, value) VALUES (?, 0) ON
            CONFLICT DO NOTHING
            """,
                (task_id,),
            )
            cursor = connection.execute(
                """
            UPDATE task_event_counters SET value = value + 1 WHERE task_id = ?
            RETURNING value
            """,
                (task_id,),
            ).fetchone()["value"]
            connection.execute(
                "INSERT INTO task_event_identities VALUES (?, ?, ?, ?)",
                (task_id, source_id, source_seq, cursor),
            )
            now = _utcnow_iso()
            connection.execute(
                """
            INSERT INTO task_event_copies ( task_id, cursor_seq, source_id,
            source_seq, event_json, created_at ) VALUES (?, ?, ?, ?, ?, ?)
            """,
                (task_id, cursor, source_id, source_seq, payload, now),
            )
        return cursor

    def list_task_events(
        self, task_id: str, *, after_cursor: int = 0
    ) -> list[tuple[int, str, int, Event]]:
        with self._read_connection() as connection:
            rows = connection.execute(
                """
            SELECT cursor_seq, source_id, source_seq, event_json FROM
            task_event_copies WHERE task_id = ? AND cursor_seq > ? ORDER BY
            cursor_seq ASC
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
        with self._write_connection() as connection:
            self._require_payload(connection, task_id)
            saved = connection.execute(
                """
            INSERT INTO task_message_receipts ( task_id, message_id, content,
            status, detail, created_at, updated_at ) VALUES (?, ?, ?, ?, ?, ?,
            ?) ON CONFLICT(task_id, message_id) DO UPDATE SET content =
            excluded.content, status = excluded.status, detail =
            excluded.detail, updated_at = excluded.updated_at WHERE
            task_message_receipts.content = excluded.content
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

    def get_task_message_receipt(
        self, task_id: str, message_id: str
    ) -> MessageReceipt | None:
        with self._read_connection() as connection:
            row = connection.execute(
                """
            SELECT * FROM task_message_receipts WHERE task_id = ? AND message_id
            = ?
            """,
                (task_id, message_id),
            ).fetchone()
        return _row_to_message_receipt(row) if row is not None else None

    def list_task_message_receipts(self, task_id: str) -> list[MessageReceipt]:
        with self._read_connection() as connection:
            rows = connection.execute(
                """
            SELECT * FROM task_message_receipts WHERE task_id = ? ORDER BY
            created_at, message_id
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
        with self._write_connection() as connection:
            self._require_payload(connection, task_id)
            now = _utcnow_iso()
            manifest_json = None if manifest is None else manifest.model_dump_json()
            connection.execute(
                """
            INSERT INTO task_results ( task_id, execution_id, manifest_json,
            evidence_complete, evidence_detail, archived_at ) VALUES (?, ?, ?,
            ?, ?, ?) ON CONFLICT(task_id) DO UPDATE SET execution_id =
            excluded.execution_id, manifest_json = excluded.manifest_json,
            evidence_complete = excluded.evidence_complete, evidence_detail =
            excluded.evidence_detail, archived_at = excluded.archived_at
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
            row = connection.execute(
                "SELECT * FROM task_results WHERE task_id = ?", (task_id,)
            ).fetchone()
        assert row is not None
        return _row_to_task_result(row)

    def get_task_result(self, task_id: str) -> TaskResultArchive | None:
        with self._read_connection() as connection:
            row = connection.execute(
                "SELECT * FROM task_results WHERE task_id = ?", (task_id,)
            ).fetchone()
        return _row_to_task_result(row) if row is not None else None

    def cancel_queued_task(self, task_id: str) -> TaskRecord | None:
        """Cancel a queued task before sandbox allocation."""
        with self._write_connection() as connection:
            row = connection.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
            if row is None:
                return None
            if TaskState(row["state"]) is not TaskState.QUEUED:
                return _row_to_record(row)
            now = _utcnow_iso()
            connection.execute(
                """
            UPDATE tasks SET state = ?, outcome_detail = ?, updated_at = ? WHERE
            id = ?
            """,
                (
                    TaskState.CANCELLED.value,
                    "cancelled_before_allocation",
                    now,
                    task_id,
                ),
            )
            updated = connection.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
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
        with self._write_connection() as connection:
            now = _utcnow_iso()
            connection.execute(
                """
            UPDATE tasks SET state = ?, outcome_detail = COALESCE(?,
            outcome_detail), check_status = COALESCE(?, check_status),
            updated_at = ?, workspace_last_activity_at = CASE WHEN ? = ? THEN
            workspace_last_activity_at ELSE ? END WHERE id = ?
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
            row = connection.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"no task {task_id}")
        return _row_to_record(row)

    def queue_workspace_message(self, task_id: str) -> None:
        """Wake a sleeping workspace after its message receipt is durable."""
        with self._write_connection() as connection:
            connection.execute(
                """
            UPDATE tasks SET state = ?, updated_at = ? WHERE id = ? AND state =
            ?
            """,
                (
                    TaskState.QUEUED.value,
                    _utcnow_iso(),
                    task_id,
                    TaskState.SLEEPING.value,
                ),
            )

    def touch_workspace(self, task_id: str) -> None:
        with self._write_connection() as connection:
            connection.execute(
                """
            UPDATE tasks SET updated_at = ?, workspace_last_activity_at = ?
            WHERE id = ?
            """,
                (_utcnow_iso(), _utcnow_iso(), task_id),
            )

    def try_mark_sleeping(self, task_id: str) -> bool:
        """Close the idle window atomically with the message queue."""
        with self._write_connection() as connection:
            pending = connection.execute(
                """
            SELECT 1 FROM task_message_receipts WHERE task_id = ? AND status = ?
            LIMIT 1
            """,
                (task_id, MessageDeliveryStatus.ACCEPTED.value),
            ).fetchone()
            if pending is not None:
                return False
            updated = connection.execute(
                """
            UPDATE tasks SET state = ?, updated_at = ? WHERE id = ? AND state =
            ?
            """,
                (
                    TaskState.SLEEPING.value,
                    _utcnow_iso(),
                    task_id,
                    TaskState.IDLE.value,
                ),
            )
            return updated.rowcount == 1

    def expire_workspace(self, task_id: str) -> None:
        with self._write_connection() as connection:
            connection.execute(
                "UPDATE tasks SET workspace_expired = 1 WHERE id = ? AND state = ?",
                (task_id, TaskState.SLEEPING.value),
            )

    def reset_sandbox_for_wake(self, task_id: str) -> None:
        """Discard the old provider identity after absence was confirmed."""
        with self._write_connection() as connection:
            connection.execute(
                """
            UPDATE sandbox_creations SET provider_id = NULL, provider_state = ?,
            detail = NULL, updated_at = ? WHERE task_id = ? AND provider_state =
            ?
            """,
                (
                    SandboxProviderState.CREATING.value,
                    _utcnow_iso(),
                    task_id,
                    SandboxProviderState.STOPPED.value,
                ),
            )

    def ping_database(self) -> bool:
        try:
            with self._read_connection() as connection:
                connection.execute("SELECT 1")
        except (sqlite3.Error, RuntimeError):
            return False
        return True

    def count_task_log_bytes(self, task_id: str) -> int:
        with self._read_connection() as connection:
            row = connection.execute(
                """
            SELECT COALESCE(( SELECT SUM(LENGTH(CAST(event_json AS BLOB))) FROM
            task_event_copies WHERE task_id = ? ), 0) + COALESCE(( SELECT
            SUM(LENGTH(CAST(content AS BLOB)) + LENGTH(CAST(COALESCE(detail, '')
            AS BLOB))) FROM task_message_receipts WHERE task_id = ? ), 0) AS
            total
            """,
                (task_id, task_id),
            ).fetchone()
        return int(row["total"])

    def count_task_artifact_bytes(self, task_id: str) -> int:
        with self._read_connection() as connection:
            row = connection.execute(
                """
            SELECT COALESCE(LENGTH(CAST(manifest_json AS BLOB)), 0) AS total
            FROM task_results WHERE task_id = ?
            """,
                (task_id,),
            ).fetchone()
        return int(row["total"]) if row is not None else 0

    def count_total_evidence_bytes(self) -> int:
        with self._read_connection() as connection:
            row = connection.execute("""
            SELECT COALESCE((SELECT SUM(LENGTH(CAST(event_json AS BLOB))) FROM
            task_event_copies), 0) + COALESCE(( SELECT SUM(LENGTH(CAST(content
            AS BLOB)) + LENGTH(CAST(COALESCE(detail, '') AS BLOB))) FROM
            task_message_receipts ), 0) + COALESCE(( SELECT
            SUM(LENGTH(CAST(manifest_json AS BLOB))) FROM task_results ), 0) AS
            total
            """).fetchone()
        return int(row["total"])

    def protected_task_ids(self) -> set[str]:
        return {item.task_id for item in self.list_reservations()}

    def expire_terminal_payloads(
        self, *, before: datetime, tombstone_retention: timedelta
    ) -> int:
        """Expire payload and mutable identities atomically, protecting reservations."""
        with self._write_connection() as connection:
            rows = connection.execute(
                """
            SELECT * FROM tasks WHERE state IN ('completed', 'failed',
            'cancelled') AND payload_expired = 0 AND updated_at < ? AND NOT
            EXISTS (SELECT 1 FROM task_reservations r WHERE r.task_id =
            tasks.id)
            """,
                (before.isoformat(),),
            ).fetchall()
            now = _utcnow_iso()
            expires = (datetime.fromisoformat(now) + tombstone_retention).isoformat()
            for row in rows:
                task_id = row["id"]
                publication = connection.execute(
                    "SELECT * FROM publication_intents WHERE task_id = ?", (task_id,)
                ).fetchone()
                remote = (
                    None
                    if publication is None
                    else json.dumps(
                        {
                            key: publication[key]
                            for key in ("pr_number", "pr_url", "pr_state", "state")
                        },
                        separators=(",", ":"),
                    )
                )
                connection.execute(
                    "INSERT INTO retention_tombstones VALUES (?, ?, ?)",
                    (task_id, remote, expires),
                )
                connection.execute(
                    """
            INSERT INTO task_idempotency (task_id, owner_id, idempotency_key,
            seq, terminal_state, model, created_at, updated_at) VALUES (?, ?, ?,
            ?, ?, ?, ?, ?)
            """,
                    (
                        task_id,
                        row["owner_id"],
                        row["idempotency_key"],
                        row["seq"],
                        row["state"],
                        row["model"],
                        row["created_at"],
                        row["updated_at"],
                    ),
                )
                for table in (
                    "task_event_copies",
                    "task_message_receipts",
                    "task_results",
                    "task_supervisions",
                    "sandbox_creations",
                    "publication_intents",
                ):
                    connection.execute(
                        f"DELETE FROM {table} WHERE task_id = ?", (task_id,)
                    )
                connection.execute(
                    """
            UPDATE tasks SET payload_expired = 1, prompt = '', repository = '',
            base_ref = NULL, base_sha = NULL, retry_of = NULL, outcome_detail =
            NULL, check_status = NULL WHERE id = ?
            """,
                    (task_id,),
                )
        return len(rows)

    def purge_expired_tombstones(self, *, before: datetime) -> int:
        with self._write_connection() as connection:
            rows = connection.execute(
                """
            SELECT task_id FROM retention_tombstones WHERE expires_at < ? AND
            NOT EXISTS (SELECT 1 FROM task_reservations r WHERE r.task_id =
            retention_tombstones.task_id)
            """,
                (before.isoformat(),),
            ).fetchall()
            for row in rows:
                connection.execute(
                    "DELETE FROM retention_tombstones WHERE task_id = ?",
                    (row["task_id"],),
                )
                connection.execute(
                    "DELETE FROM tasks WHERE id = ? AND payload_expired = 1",
                    (row["task_id"],),
                )
        return len(rows)

    @staticmethod
    def _record_from_tombstone(row: dict[str, Any]) -> TaskRecord:
        return TaskRecord(
            owner_id=row["owner_id"],
            id=row["task_id"],
            seq=row["seq"],
            state=TaskState(row["terminal_state"]),
            idempotency_key=row["idempotency_key"],
            prompt="",
            model=row["model"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            payload_expired=True,
        )

    @staticmethod
    def _require_payload(connection: sqlite3.Connection, task_id: str) -> None:
        row = connection.execute(
            "SELECT payload_expired FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if row is None or row["payload_expired"]:
            raise KeyError(f"no active task payload {task_id}")


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
