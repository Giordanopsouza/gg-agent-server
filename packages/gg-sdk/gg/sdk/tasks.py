"""Frozen domain models for durable background tasks.

These types are shared across the SDK and the runtime control plane. They are
frozen Pydantic models so that request identity and task state cannot be mutated
in place after admission. The runtime owns persistence; the SDK never imports
``gg.server`` or ``gg.runtime``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class TaskState(StrEnum):
    """Lifecycle of one background task, persisted in the ledger."""

    QUEUED = "queued"
    STARTING = "starting"
    RUNNING = "running"
    FINALIZING = "finalizing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CreateTaskRequest(BaseModel):
    """HTTP submission payload for ``POST /tasks``.

    ``idempotency_key`` is required: the runtime returns the original task for
    identical replays and rejects reuse with different input as a conflict.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    repository: str
    prompt: str
    idempotency_key: str = Field(min_length=1, max_length=256)
    base_ref: str | None = None
    retry_of: str | None = None


class TaskRecord(BaseModel):
    """Durable snapshot of one background task returned by the API."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    seq: int
    state: TaskState = TaskState.QUEUED
    idempotency_key: str
    repository: str
    prompt: str
    base_ref: str | None = None
    base_sha: str | None = None
    retry_of: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    # Outcome, check, and cleanup status are stored separately so that a failed
    # sandbox cleanup cannot be confused with a failed task outcome.
    outcome_detail: str | None = None
    check_status: str | None = None
    sandbox_cleanup_status: str | None = None
    payload_expired: bool = False


__all__ = ["CreateTaskRequest", "TaskRecord", "TaskState"]
