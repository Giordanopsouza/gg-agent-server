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
from gg.sdk.tasks import CreateTaskRequest, TaskRecord


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

    # Whether a stored task matches the resubmitted request identity.
    @staticmethod
    def _matches_existing(existing: TaskRecord, request: CreateTaskRequest) -> bool:
        return (
            existing.repository == request.repository
            and existing.prompt == request.prompt
            and existing.base_ref == request.base_ref
            and existing.retry_of == request.retry_of
        )


__all__ = ["TaskConflictError", "TaskService", "TaskValidationError"]
