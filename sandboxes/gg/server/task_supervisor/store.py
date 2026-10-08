"""Atomic persistence for execution identity and result manifests."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from gg.sdk.agent_backend import DEFAULT_PI_MODEL
from gg.sdk.task_execution import (
    TaskExecutionPhase,
    TaskExecutionRecord,
    TaskResultManifest,
)
from gg.server.sqlite_state import SandboxState


class StartKeyConflictError(Exception):
    """Raised when a start key is reused with different task identity."""


class ExecutionStore:
    """SQLite execution identity and evidence shared across supervisor restarts."""

    def __init__(self, root: Path, *, state_db: SandboxState | None = None) -> None:
        self.state_db = state_db or SandboxState(root / "sandbox.db")

    def conversation_id(self) -> str:
        """Bind the workspace generation to one conversation, atomically."""
        with self.state_db.write() as connection:
            row = connection.execute(
                "SELECT value FROM sandbox_metadata WHERE name = 'conversation-id'"
            ).fetchone()
            if row is not None:
                return row[0]
            value = str(uuid4())
            connection.execute(
                "INSERT INTO sandbox_metadata VALUES ('conversation-id', ?)", (value,)
            )
        return value

    def admit_or_get(
        self,
        *,
        start_key: str,
        task_id: str,
        repository: str | None,
        task_branch: str | None,
        base_ref: str | None,
        deadline_at: datetime,
        model: str = DEFAULT_PI_MODEL,
    ) -> tuple[TaskExecutionRecord, bool]:
        with self.state_db.write() as connection:
            row = connection.execute(
                "SELECT payload FROM executions WHERE start_key = ?", (start_key,)
            ).fetchone()
            if row is not None:
                record = TaskExecutionRecord.model_validate_json(row[0])
                if (
                    record.task_id,
                    record.repository,
                    record.task_branch,
                    record.base_ref,
                    record.model,
                ) != (task_id, repository, task_branch, base_ref, model):
                    raise StartKeyConflictError(
                        f"start_key {start_key!r} already bound to another execution"
                    )
                return record, False
            now = datetime.now(UTC)
            record = TaskExecutionRecord(
                execution_id=self._new_execution_id(task_id, start_key),
                task_id=task_id,
                repository=repository,
                start_key=start_key,
                task_branch=task_branch,
                base_ref=base_ref,
                deadline_at=deadline_at,
                model=model,
                created_at=now,
                updated_at=now,
            )
            connection.execute(
                "INSERT INTO executions VALUES (?, ?, ?, ?)",
                (
                    record.execution_id,
                    start_key,
                    record.phase.value,
                    record.model_dump_json(),
                ),
            )
        return record, True

    def load_execution(self, execution_id: str) -> TaskExecutionRecord:
        with self.state_db.connection() as connection:
            row = connection.execute(
                "SELECT payload FROM executions WHERE execution_id = ?", (execution_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown execution {execution_id}")
        return TaskExecutionRecord.model_validate_json(row[0])

    def save_execution(self, record: TaskExecutionRecord) -> None:
        with self.state_db.write() as connection:
            row = connection.execute(
                "SELECT payload FROM executions WHERE execution_id = ?",
                (record.execution_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown execution {record.execution_id}")
            existing = TaskExecutionRecord.model_validate_json(row[0])
            if (
                existing.start_key,
                existing.task_id,
                existing.repository,
                existing.task_branch,
                existing.base_ref,
                existing.model,
            ) != (
                record.start_key,
                record.task_id,
                record.repository,
                record.task_branch,
                record.base_ref,
                record.model,
            ):
                raise StartKeyConflictError("cannot change execution identity")
            connection.execute(
                "UPDATE executions SET phase = ?, payload = ? WHERE execution_id = ?",
                (record.phase.value, record.model_dump_json(), record.execution_id),
            )

    def save_manifest(self, manifest: TaskResultManifest) -> str:
        with self.state_db.write() as connection:
            connection.execute(
                """INSERT INTO manifests VALUES (?, ?) ON CONFLICT(execution_id)
                   DO UPDATE SET payload = excluded.payload""",
                (manifest.execution_id, manifest.model_dump_json()),
            )
        return self.manifest_reference(manifest.execution_id)

    def manifest_reference(self, execution_id: str) -> str:
        return f"sqlite:{self.state_db.path}#manifest/{execution_id}"

    def load_manifest(self, execution_id: str) -> TaskResultManifest:
        with self.state_db.connection() as connection:
            row = connection.execute(
                "SELECT payload FROM manifests WHERE execution_id = ?", (execution_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"no manifest for execution {execution_id}")
        return TaskResultManifest.model_validate_json(row[0])

    def list_non_terminal(self) -> list[TaskExecutionRecord]:
        with self.state_db.connection() as connection:
            rows = connection.execute(
                """SELECT payload FROM executions WHERE phase NOT IN (?, ?)
                   ORDER BY execution_id""",
                (TaskExecutionPhase.COMPLETED.value, TaskExecutionPhase.FAILED.value),
            ).fetchall()
        return [TaskExecutionRecord.model_validate_json(row[0]) for row in rows]

    @staticmethod
    def _new_execution_id(task_id: str, start_key: str) -> str:
        return hashlib.sha256(f"{task_id}:{start_key}".encode()).hexdigest()[:32]


__all__ = ["ExecutionStore", "StartKeyConflictError"]
