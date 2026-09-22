"""Shared models for sandbox task execution and result evidence."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class TaskExecutionPhase(StrEnum):
    """High-level progress for one sandbox execution attempt."""

    ACCEPTED = "accepted"
    PREPARING = "preparing"
    RUNNING_AGENT = "running_agent"
    RUNNING_CHECKS = "running_checks"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentOutcome(StrEnum):
    """How the Pi conversation finished."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"
    NO_CHANGES = "no_changes"
    NOT_RUN = "not_run"


class CheckOutcome(StrEnum):
    """Measured check command result."""

    PASSED = "passed"
    FAILED = "failed"
    NOT_RUN = "not_run"
    TIMEOUT = "timeout"


class CommandCapture(BaseModel):
    """Bounded output from one shell command."""

    model_config = ConfigDict(frozen=True)

    command: str
    exit_code: int | None
    duration_ms: int
    stdout: str
    stderr: str
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    timed_out: bool = False


class TaskResultManifest(BaseModel):
    """Durable local evidence for one task run."""

    model_config = ConfigDict(frozen=True)

    task_id: str
    execution_id: str
    repository: str | None = None
    task_branch: str | None = None
    base_ref: str | None = None
    base_sha: str | None = None
    head_sha: str | None = None
    changed_files: tuple[str, ...] = ()
    patch: str | None = None
    patch_truncated: bool = False
    bootstrap: CommandCapture | None = None
    check: CommandCapture | None = None
    check_outcome: CheckOutcome = CheckOutcome.NOT_RUN
    agent_outcome: AgentOutcome = AgentOutcome.NOT_RUN
    conversation_id: str | None = None
    outcome_detail: str | None = None
    completed_at: datetime | None = None


class StartTaskExecutionRequest(BaseModel):
    """Nonblocking execution startup payload."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: str = Field(min_length=1, max_length=128)
    repository: str | None = None
    prompt: str = Field(min_length=1)
    base_ref: str | None = None
    task_branch: str | None = Field(default=None, min_length=1, max_length=256)
    start_key: str = Field(min_length=1, max_length=256)
    deadline_at: datetime


class TaskExecutionRecord(BaseModel):
    """Public execution identity returned by the sandbox supervisor."""

    model_config = ConfigDict(frozen=True)

    execution_id: str = Field(default_factory=lambda: str(uuid4()))
    task_id: str
    repository: str | None = None
    start_key: str
    phase: TaskExecutionPhase = TaskExecutionPhase.ACCEPTED
    task_branch: str | None = None
    base_ref: str | None = None
    deadline_at: datetime
    conversation_id: str | None = None
    manifest_path: str | None = None
    outcome_detail: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


__all__ = [
    "AgentOutcome",
    "CheckOutcome",
    "CommandCapture",
    "StartTaskExecutionRequest",
    "TaskExecutionPhase",
    "TaskExecutionRecord",
    "TaskResultManifest",
]
