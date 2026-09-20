from __future__ import annotations

import pytest
from pydantic import ValidationError

from gg.sdk.tasks import CreateTaskRequest, TaskRecord, TaskState


def test_task_state_covers_full_lifecycle() -> None:
    expected = {
        "queued",
        "starting",
        "running",
        "finalizing",
        "completed",
        "failed",
        "cancelled",
    }
    assert {state.value for state in TaskState} == expected


def test_create_task_request_is_frozen_and_requires_idempotency_key() -> None:
    request = CreateTaskRequest(
        repository="owner/name",
        prompt="fix the bug",
        idempotency_key="key-1",
    )
    assert request.base_ref is None
    assert request.retry_of is None
    with pytest.raises(ValidationError):
        request.prompt = "mutated"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        CreateTaskRequest(
            repository="owner/name",
            prompt="fix the bug",
            idempotency_key="",
        )


def test_create_task_request_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        CreateTaskRequest(
            repository="owner/name",
            prompt="fix the bug",
            idempotency_key="key-1",
            sandbox_id="extra",  # type: ignore[call-arg]
        )


def test_task_record_defaults_to_queued_with_separate_status_fields() -> None:
    record = TaskRecord(
        seq=1, idempotency_key="key-1", repository="owner/name", prompt="p"
    )
    assert record.state is TaskState.QUEUED
    assert record.base_sha is None
    assert record.outcome_detail is None
    assert record.check_status is None
    assert record.sandbox_cleanup_status is None
    assert record.id
