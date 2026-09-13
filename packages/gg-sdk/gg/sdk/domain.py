from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from gg.sdk.agent_backend import AgentConfig, PiAgentConfig


class ConversationStatus(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    FINISHED = "finished"
    ERROR = "error"


class EventKind(StrEnum):
    MESSAGE = "message"
    ACTION = "action"
    OBSERVATION = "observation"
    STATUS = "status"
    ERROR = "error"


class Event(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    seq: int
    kind: EventKind
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ConversationRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    status: ConversationStatus
    working_dir: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class StartConversationRequest(BaseModel):
    """HTTP create/reattach payload. Parsed at the router, not as a raw dict."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    working_dir: str
    id: str | None = None
    agent: AgentConfig = Field(default_factory=PiAgentConfig)


class SendMessageRequest(BaseModel):
    """HTTP send-message payload. REST defaults to run=false, matching OpenHands."""

    model_config = ConfigDict(frozen=True)

    content: str
    run: bool = False
