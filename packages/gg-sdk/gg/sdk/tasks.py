"""Frozen domain models for durable background tasks.

These types are shared across the SDK and the runtime control plane. They are
frozen Pydantic models so that request identity and task state cannot be mutated
in place after admission. The runtime owns persistence; the SDK never imports
``gg.server`` or ``gg.runtime``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from gg.sdk.agent_backend import DEFAULT_PI_MODEL


class TaskState(StrEnum):
    """Lifecycle of one background task, persisted in the ledger."""

    QUEUED = "queued"
    STARTING = "starting"
    RUNNING = "running"
    IDLE = "idle"
    SLEEPING = "sleeping"
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

    repository: str | None = None
    prompt: str
    idempotency_key: str = Field(min_length=1, max_length=256)
    base_ref: str | None = None
    retry_of: str | None = None
    model: str = DEFAULT_PI_MODEL


class TaskRecord(BaseModel):
    """Durable snapshot of one background task returned by the API."""

    model_config = ConfigDict(frozen=True)

    owner_id: UUID | None = None

    id: str = Field(default_factory=lambda: str(uuid4()))
    seq: int
    state: TaskState = TaskState.QUEUED
    idempotency_key: str
    repository: str | None = None
    prompt: str
    base_ref: str | None = None
    base_sha: str | None = None
    retry_of: str | None = None
    model: str = DEFAULT_PI_MODEL
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    # Outcome, check, and cleanup status are stored separately so that a failed
    # sandbox cleanup cannot be confused with a failed task outcome.
    agent_outcome: str | None = None
    outcome_detail: str | None = None
    check_status: str | None = None
    sandbox_cleanup_status: str | None = None
    payload_expired: bool = False
    workspace_expired: bool = False
    workspace_last_activity_at: datetime | None = None


__all__ = ["CreateTaskRequest", "TaskRecord", "TaskState"]
