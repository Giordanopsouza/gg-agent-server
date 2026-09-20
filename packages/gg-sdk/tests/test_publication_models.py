from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from gg.sdk.publication import PublicationRecord, PublicationRequest, PublicationState
from gg.sdk.task_execution import AgentOutcome, CheckOutcome


def test_publication_request_is_frozen() -> None:
    request = PublicationRequest(
        task_id="task-1",
        repository="owner/repo",
        task_branch="gg/task/task-1",
        base_ref="main",
        base_sha="abc123",
        task_marker="task:task-1",
        agent_outcome=AgentOutcome.SUCCEEDED,
        check_outcome=CheckOutcome.PASSED,
        changed_files=("README.md",),
    )
    with pytest.raises(ValidationError):
        request.task_branch = "main"  # type: ignore[misc]


def test_publication_record_omits_credentials_in_dump() -> None:
    record = PublicationRecord(
        task_id="task-1",
        repository="owner/repo",
        task_branch="gg/task/task-1",
        base_ref="main",
        task_marker="task:task-1",
        state=PublicationState.PUBLISHED,
        commit_sha="def456",
        pr_number=12,
        pr_url="https://github.com/owner/repo/pull/12",
        pr_draft=True,
        pr_author="gg-bot",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    dumped = record.model_dump()
    assert "token" not in dumped
    assert "secret" not in str(dumped).lower()
    assert record.pr_draft is True
