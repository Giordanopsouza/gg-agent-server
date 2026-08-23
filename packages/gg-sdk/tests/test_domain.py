from __future__ import annotations

import pytest
from pydantic import ValidationError

from gg.sdk import (
    ConversationRecord,
    ConversationStatus,
    Event,
    EventKind,
    StartConversationRequest,
)


@pytest.mark.parametrize("status", list(ConversationStatus))
def test_conversation_record_accepts_valid_status(
    status: ConversationStatus,
) -> None:
    record = ConversationRecord.model_validate(
        {
            "id": "test-id",
            "status": status.value,
            "working_dir": "/tmp/work",
            "created_at": "2026-08-21T12:00:00+00:00",
        }
    )
    assert record.status == status


def test_conversation_record_rejects_invalid_status() -> None:
    with pytest.raises(ValidationError):
        ConversationRecord.model_validate(
            {
                "id": "test-id",
                "status": "paused",
                "working_dir": "/tmp/work",
                "created_at": "2026-08-21T12:00:00+00:00",
            }
        )


def test_start_conversation_request_requires_working_dir() -> None:
    request = StartConversationRequest.model_validate({"working_dir": "/tmp/work"})
    assert request.working_dir == "/tmp/work"
    assert request.id is None
    with pytest.raises(ValidationError):
        StartConversationRequest.model_validate({})


def test_event_fields() -> None:
    event = Event(
        seq=1,
        kind=EventKind.MESSAGE,
        payload={"text": "hello"},
    )
    assert event.seq == 1
    assert event.kind == EventKind.MESSAGE
    assert event.payload == {"text": "hello"}
    assert event.id
    assert event.created_at.tzinfo is not None