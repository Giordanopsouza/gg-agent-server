"""Frozen models for one-task draft PR publication.

The control plane owns the durable journal; these types are the shared
identity of a publication attempt. They never include credentials.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from gg.sdk.task_execution import AgentOutcome, CheckOutcome, CommandCapture


class PublicationState(StrEnum):
    """Durable progress of one task's publication attempt."""

    PENDING = "pending"
    PUSHED = "pushed"
    CREATING = "creating"
    PUBLISHED = "published"
    SKIPPED = "skipped"
    FAILED = "failed"


class PublicationRequest(BaseModel):
    """Inputs required to commit, push, and reconcile one draft PR."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: str = Field(min_length=1, max_length=128)
    repository: str
    task_branch: str = Field(min_length=1, max_length=256)
    base_ref: str = Field(min_length=1, max_length=200)
    base_sha: str = Field(min_length=1)
    task_marker: str = Field(min_length=1, max_length=256)
    agent_outcome: AgentOutcome
    check_outcome: CheckOutcome = CheckOutcome.NOT_RUN
    check: CommandCapture | None = None
    changed_files: tuple[str, ...] = ()


class PublicationRecord(BaseModel):
    """Credential-free snapshot of one task's publication journal row."""

    model_config = ConfigDict(frozen=True)

    task_id: str
    repository: str
    task_branch: str
    base_ref: str
    task_marker: str
    state: PublicationState
    commit_sha: str | None = None
    check_outcome: CheckOutcome = CheckOutcome.NOT_RUN
    agent_outcome: AgentOutcome = AgentOutcome.NOT_RUN
    pr_number: int | None = None
    pr_url: str | None = None
    pr_draft: bool | None = None
    pr_author: str | None = None
    pr_state: str | None = None
    detail: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


__all__ = [
    "PublicationRecord",
    "PublicationRequest",
    "PublicationState",
]
