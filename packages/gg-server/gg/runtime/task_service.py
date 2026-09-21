"""Application service over the task ledger.

Validates submission input against runtime settings, enforces idempotency
semantics (identical replay returns the original task; reuse with different
input is a conflict), and exposes list/get to route handlers. The service
never imports ``gg.server``; it depends only on the SDK models and the
ledger.
"""

from __future__ import annotations

import re

from gg.runtime.config import RuntimeSettings
from gg.runtime.ledger import TaskLedger
from gg.runtime.storage import StorageLimits, admission_pressure
from gg.sdk.task_supervision import RetryTaskRequest, TaskResultRecord
from gg.sdk.tasks import CreateTaskRequest, TaskRecord, TaskState


# owner/name style repository identifier.
_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")
# Git ref: alphanumeric start, then a bounded run of allowed chars, no "..".
_BASE_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")


class TaskConflictError(Exception):
    """Raised when an idempotency key is reused with different input."""

    def __init__(self, existing: TaskRecord) -> None:
        super().__init__(
            f"idempotency key {existing.idempotency_key!r} already used by task "
            f"{existing.id}"
        )
        self.existing = existing


class TaskValidationError(ValueError):
    """Raised when a submission fails input validation."""


class TaskControlError(RuntimeError):
    """Raised when cancel, retry, or messaging preconditions fail."""


class StoragePressureError(RuntimeError):
    """Raised when storage limits block new admissions."""


class TaskService:
    """Validate and durably admit background tasks."""

    def __init__(self, *, ledger: TaskLedger, settings: RuntimeSettings) -> None:
        self._ledger = ledger
        self._settings = settings

    # Validate one submission request against the configured limits.
    def validate(self, request: CreateTaskRequest) -> None:
        if not request.repository or not _REPOSITORY_RE.match(request.repository):
            raise TaskValidationError(
                f"repository must be 'owner/name', got {request.repository!r}"
            )
        if (
            self._settings.repository_allowlist
            and request.repository not in self._settings.repository_allowlist
        ):
            raise TaskValidationError(
                f"repository {request.repository!r} is not on the allowlist"
            )
        if self._settings.repository_profiles:
            known = {
                profile.repository for profile in self._settings.repository_profiles
            }
            if request.repository not in known:
                raise TaskValidationError(
                    f"repository {request.repository!r} has no configured profile"
                )
        if not request.prompt.strip():
            raise TaskValidationError("prompt must be non-empty")
        if len(request.prompt) > self._settings.max_prompt_chars:
            raise TaskValidationError(
                f"prompt length {len(request.prompt)} exceeds "
                f"max {self._settings.max_prompt_chars}"
            )
        if not request.idempotency_key or not request.idempotency_key.strip():
            raise TaskValidationError("idempotency_key must be non-empty")
        if len(request.idempotency_key) > self._settings.max_idempotency_key_chars:
            raise TaskValidationError(
                f"idempotency_key length {len(request.idempotency_key)} exceeds "
                f"max {self._settings.max_idempotency_key_chars}"
            )
        if request.base_ref is not None:
            if not _BASE_REF_RE.match(request.base_ref):
                raise TaskValidationError(
                    f"base_ref {request.base_ref!r} is not a valid git ref"
                )
            if ".." in request.base_ref:
                raise TaskValidationError(
                    f"base_ref {request.base_ref!r} must not contain '..'"
                )
            if len(request.base_ref) > self._settings.max_base_ref_chars:
                raise TaskValidationError(
                    f"base_ref length {len(request.base_ref)} exceeds "
                    f"max {self._settings.max_base_ref_chars}"
                )

    # Validate, then durably submit. Returns (record, created).
    def submit(self, request: CreateTaskRequest) -> tuple[TaskRecord, bool]:
        self.validate(request)
        limits = StorageLimits.from_settings(self._settings)
        pressure = admission_pressure(
            self._ledger,
            limits,
            db_path=self._settings.task_db_path,
        )
        if pressure.blocked:
            raise StoragePressureError(pressure.reason or "storage pressure")
        record, created = self._ledger.submit(
            idempotency_key=request.idempotency_key,
            repository=request.repository,
            prompt=request.prompt,
            base_ref=request.base_ref,
            retry_of=request.retry_of,
        )
        if not created and not self._matches_existing(record, request):
            raise TaskConflictError(record)
        return record, created

    # Return all tasks in FIFO order.
    def list(self) -> list[TaskRecord]:
        return self._ledger.list()

    # Return one task by id, or None.
    def get(self, task_id: str) -> TaskRecord | None:
        return self._ledger.get(task_id)

    def cancel(self, task_id: str) -> TaskRecord:
        record = self._ledger.get(task_id)
        if record is None:
            raise TaskControlError(f"unknown task {task_id}")
        if record.state is TaskState.CANCELLED:
            return record
        if record.state is TaskState.QUEUED:
            cancelled = self._ledger.cancel_queued_task(task_id)
            assert cancelled is not None
            return cancelled
        if record.state not in {TaskState.STARTING, TaskState.RUNNING}:
            raise TaskControlError(
                f"task {task_id} in state {record.state} cannot be cancelled"
            )
        self._ledger.request_task_cancel(task_id)
        return self._ledger.get(task_id) or record

    def retry(self, task_id: str, request: RetryTaskRequest) -> tuple[TaskRecord, bool]:
        predecessor = self._ledger.get(task_id)
        if predecessor is None:
            raise TaskControlError(f"unknown task {task_id}")
        if predecessor.state not in {
            TaskState.COMPLETED,
            TaskState.FAILED,
            TaskState.CANCELLED,
        }:
            raise TaskControlError("retry is only available after terminal execution")
        if predecessor.sandbox_cleanup_status != "confirmed_absent":
            raise TaskControlError(
                "retry requires confirmed sandbox cleanup of the predecessor"
            )
        base_ref = request.base_ref or predecessor.base_ref
        if base_ref is None and predecessor.base_sha is None:
            raise TaskControlError(
                "retry requires a recorded base ref or explicit base_ref"
            )
        create = CreateTaskRequest(
            repository=predecessor.repository,
            prompt=predecessor.prompt,
            idempotency_key=request.idempotency_key,
            base_ref=base_ref,
            retry_of=task_id,
        )
        return self.submit(create)

    def result(self, task_id: str) -> TaskResultRecord:
        record = self._ledger.get(task_id)
        if record is None:
            raise TaskControlError(f"unknown task {task_id}")
        archive = self._ledger.get_task_result(task_id)
        publication = self._ledger.get_publication(task_id)
        supervision = self._ledger.get_supervision(task_id)
        prior_branch = supervision.task_branch if supervision else None
        prior_pr = publication.pr_url if publication else None
        return TaskResultRecord(
            task_id=record.id,
            state=record.state,
            execution_id=archive.execution_id if archive else None,
            manifest=archive.manifest if archive else None,
            publication=publication,
            evidence_complete=archive.evidence_complete if archive else False,
            evidence_detail=archive.evidence_detail if archive else None,
            sandbox_cleanup_status=record.sandbox_cleanup_status,
            outcome_detail=record.outcome_detail,
            check_status=record.check_status,
            retry_of=record.retry_of,
            prior_task_branch=prior_branch,
            prior_pr_url=prior_pr,
            updated_at=record.updated_at,
        )

    # Whether a stored task matches the resubmitted request identity.
    @staticmethod
    def _matches_existing(existing: TaskRecord, request: CreateTaskRequest) -> bool:
        return (
            existing.repository == request.repository
            and existing.prompt == request.prompt
            and existing.base_ref == request.base_ref
            and existing.retry_of == request.retry_of
        )


__all__ = [
    "StoragePressureError",
    "TaskConflictError",
    "TaskControlError",
    "TaskService",
    "TaskValidationError",
]
