from __future__ import annotations

import pytest

from gg.sdk.task_supervision import RetryTaskRequest, TaskMessageRequest


def test_task_message_request_is_frozen() -> None:
    request = TaskMessageRequest(id="m1", content="hello")
    with pytest.raises(Exception):
        request.id = "m2"  # type: ignore[misc]


def test_retry_request_requires_idempotency_key() -> None:
    RetryTaskRequest(idempotency_key="retry-1", base_ref="main")
