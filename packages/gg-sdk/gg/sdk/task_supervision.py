"""Frozen models for control-plane task supervision and public results."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from gg.sdk.domain import Event
from gg.sdk.publication import PublicationRecord
from gg.sdk.task_execution import TaskResultManifest
from gg.sdk.tasks import TaskState


class TaskEventCopy(BaseModel):
    """One conversation event copied durably to the control plane."""

    model_config = ConfigDict(frozen=True)

    cursor: int = Field(ge=1)
    source_id: str = Field(min_length=1)
    source_seq: int = Field(ge=1)
    event: Event


class TaskMessageRequest(BaseModel):
    """Idempotent steer payload for a running background task."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)


class RetryTaskRequest(BaseModel):
    """Explicit retry after terminal execution and confirmed cleanup."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    idempotency_key: str = Field(min_length=1, max_length=256)
    base_ref: str | None = None


class TaskResultRecord(BaseModel):
    """Public task outcome, evidence, and publication references."""

    model_config = ConfigDict(frozen=True)

    task_id: str
    state: TaskState
    execution_id: str | None = None
    manifest: TaskResultManifest | None = None
    publication: PublicationRecord | None = None
    evidence_complete: bool = False
    evidence_detail: str | None = None
    sandbox_cleanup_status: str | None = None
    outcome_detail: str | None = None
    check_status: str | None = None
    retry_of: str | None = None
    prior_task_branch: str | None = None
    prior_pr_url: str | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


__all__ = [
    "RetryTaskRequest",
    "TaskEventCopy",
    "TaskMessageRequest",
    "TaskResultRecord",
]
