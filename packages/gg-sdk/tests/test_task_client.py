from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from websockets.exceptions import InvalidStatus

import gg.sdk.task_client as task_client_module
from gg.sdk.domain import Event, EventKind, MessageDeliveryStatus
from gg.sdk.task_client import TaskClient, TaskClientError, TaskNotFoundError
from gg.sdk.task_settings import TaskClientSettings
from gg.sdk.task_supervision import (
    TaskEventCopy,
    TaskMessageRequest,
    TaskResultRecord,
)
from gg.sdk.tasks import CreateTaskRequest, TaskState


def _settings() -> TaskClientSettings:
    return TaskClientSettings(api_url="http://127.0.0.1:8001", api_key="control-secret")


def _task(task_id: str = "task-1") -> dict[str, Any]:
    now = datetime.now(UTC).isoformat()
    return {
        "id": task_id,
        "seq": 1,
        "state": "queued",
        "idempotency_key": "k1",
        "repository": "owner/repo",
        "prompt": "fix",
        "base_ref": None,
        "base_sha": None,
        "retry_of": None,
        "created_at": now,
        "updated_at": now,
        "outcome_detail": None,
        "check_status": None,
        "sandbox_cleanup_status": None,
    }


def test_submit_and_idempotent_replay() -> None:
    calls = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.headers.get("x-api-key") == "control-secret"
        status = 201 if calls == 1 else 200
        return httpx.Response(status, json=_task())

    transport = httpx.MockTransport(handle)
    with httpx.Client(transport=transport, base_url="http://127.0.0.1:8001") as http:
        client = TaskClient(_settings(), client=http)
        first = client.submit(
            CreateTaskRequest(
                repository="owner/repo",
                prompt="fix",
                idempotency_key="k1",
            )
        )
        second = client.submit(
            CreateTaskRequest(
                repository="owner/repo",
                prompt="fix",
                idempotency_key="k1",
            )
        )

    assert first.created is True
    assert second.created is False
    assert first.record.id == "task-1"


def test_get_task_not_found() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "not found"})

    transport = httpx.MockTransport(handle)
    with httpx.Client(transport=transport, base_url="http://127.0.0.1:8001") as http:
        client = TaskClient(_settings(), client=http)
        with pytest.raises(TaskNotFoundError):
            client.get_task("missing")


def test_message_conflict_surfaces_detail() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"detail": "task is not accepting messages"})

    transport = httpx.MockTransport(handle)
    with httpx.Client(transport=transport, base_url="http://127.0.0.1:8001") as http:
        client = TaskClient(_settings(), client=http)
        with pytest.raises(TaskClientError) as exc:
            client.send_message(
                "task-1",
                TaskMessageRequest(id="m1", content="hi"),
            )
    assert exc.value.status_code == 409


def test_subscription_builds_task_event_websocket_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = Event(seq=1, kind=EventKind.STATUS, payload={"status": "running"})
    copy = TaskEventCopy(cursor=1, source_id="task-1", source_seq=1, event=event)

    class FakeConnection:
        def recv(self, *, timeout: float | None = None) -> str:
            return copy.model_dump_json()

        def close(self) -> None:
            return None

    connected: list[tuple[str, dict[str, str]]] = []

    def fake_connect(url: str, **kwargs: Any) -> FakeConnection:
        connected.append((url, kwargs.get("additional_headers") or {}))
        return FakeConnection()

    monkeypatch.setattr(task_client_module, "connect", fake_connect)
    client = TaskClient(_settings())
    with client.subscribe_events("task-1", after=0) as subscription:
        received = subscription.receive()
    client.close()

    assert connected == [
        (
            "ws://127.0.0.1:8001/tasks/sockets/events/task-1",
            {"X-API-Key": "control-secret"},
        )
    ]
    assert received.cursor == 1
    assert subscription.cursor == 1


def test_subscription_maps_rejected_handshake_to_client_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Rejected:
        status_code = 401

    def fake_connect(*_: Any, **__: Any) -> None:
        raise InvalidStatus(_Rejected())  # type: ignore[arg-type]

    monkeypatch.setattr(task_client_module, "connect", fake_connect)
    client = TaskClient(_settings())
    with pytest.raises(TaskClientError) as exc:
        with client.subscribe_events("task-1"):
            pass
    client.close()

    assert exc.value.status_code == 401
    assert "HTTP 401" in exc.value.detail


def test_result_parses_public_fields() -> None:
    payload = {
        "task_id": "task-1",
        "state": "failed",
        "execution_id": "exec-1",
        "manifest": None,
        "publication": None,
        "evidence_complete": False,
        "evidence_detail": "logs truncated",
        "sandbox_cleanup_status": "confirmed_absent",
        "outcome_detail": "agent failed",
        "check_status": "failed",
        "retry_of": None,
        "prior_task_branch": "gg/task/task-0",
        "prior_pr_url": "https://github.com/o/r/pull/1",
        "updated_at": datetime.now(UTC).isoformat(),
    }

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(handle)
    with httpx.Client(transport=transport, base_url="http://127.0.0.1:8001") as http:
        client = TaskClient(_settings(), client=http)
        result = client.result("task-1")

    assert isinstance(result, TaskResultRecord)
    assert result.prior_pr_url == "https://github.com/o/r/pull/1"


def test_cancel_and_list_tasks() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/tasks":
            return httpx.Response(200, json=[_task()])
        if request.url.path.endswith("/cancel"):
            body = _task()
            body["state"] = "cancelled"
            return httpx.Response(200, json=body)
        raise AssertionError(request.url.path)

    transport = httpx.MockTransport(handle)
    with httpx.Client(transport=transport, base_url="http://127.0.0.1:8001") as http:
        client = TaskClient(_settings(), client=http)
        listed = client.list_tasks()
        cancelled = client.cancel("task-1")

    assert listed[0].state is TaskState.QUEUED
    assert cancelled.state is TaskState.CANCELLED


def test_get_message_receipt() -> None:
    receipt = {
        "id": "m1",
        "content": "hi",
        "status": MessageDeliveryStatus.DELIVERED,
        "detail": None,
        "created_at": datetime.now(UTC).isoformat(),
        "updated_at": datetime.now(UTC).isoformat(),
    }

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=receipt)

    transport = httpx.MockTransport(handle)
    with httpx.Client(transport=transport, base_url="http://127.0.0.1:8001") as http:
        client = TaskClient(_settings(), client=http)
        loaded = client.get_message_receipt("task-1", "m1")

    assert loaded.status is MessageDeliveryStatus.DELIVERED
