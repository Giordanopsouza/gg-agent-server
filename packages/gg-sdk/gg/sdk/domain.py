from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


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
