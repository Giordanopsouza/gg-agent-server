"""HTTP and WebSocket client for the runtime background-task API."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from types import TracebackType
from urllib.parse import urlsplit, urlunsplit

import httpx
from websockets.exceptions import InvalidStatus
from websockets.sync.client import ClientConnection, connect

from gg.sdk.domain import MessageReceipt
from gg.sdk.task_settings import TaskClientSettings
from gg.sdk.task_supervision import (
    RetryTaskRequest,
    TaskEventCopy,
    TaskMessageRequest,
    TaskResultRecord,
)
from gg.sdk.tasks import CreateTaskRequest, TaskRecord


RUNTIME_API_KEY_HEADER = "X-API-Key"


class TaskClientError(Exception):
    """The control plane rejected a task client request."""

    def __init__(self, *, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"HTTP {status_code}: {detail}")


class TaskNotFoundError(TaskClientError):
    """No task exists for the requested id."""


def _missing_task(task_id: str) -> TaskNotFoundError:
    return TaskNotFoundError(status_code=404, detail=f"task not found: {task_id}")


@dataclass(frozen=True)
class SubmitResponse:
    """One task submission and whether the server created a new row."""

    record: TaskRecord
    created: bool


class TaskClient:
    """Synchronous client over authenticated runtime task routes."""

    def __init__(
        self,
        settings: TaskClientSettings,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self.settings = settings
        if client is None:
            self._client = httpx.Client(
                base_url=settings.api_url,
                headers={RUNTIME_API_KEY_HEADER: settings.api_key},
                timeout=settings.timeout,
            )
            self._owns_client = True
        else:
            self._client = client
            self._client.headers.setdefault(RUNTIME_API_KEY_HEADER, settings.api_key)
            self._owns_client = False

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> TaskClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def submit(self, request: CreateTaskRequest) -> SubmitResponse:
        response = self._client.post("/tasks", json=request.model_dump(mode="json"))
        if response.status_code in {200, 201}:
            record = TaskRecord.model_validate(response.json())
            return SubmitResponse(record=record, created=response.status_code == 201)
        raise _api_error(response)

    def list_tasks(self) -> list[TaskRecord]:
        response = self._client.get("/tasks")
        if response.status_code == 200:
            return [TaskRecord.model_validate(item) for item in response.json()]
        raise _api_error(response)

    def get_task(self, task_id: str) -> TaskRecord:
        response = self._client.get(f"/tasks/{task_id}")
        if response.status_code == 200:
            return TaskRecord.model_validate(response.json())
        if response.status_code == 404:
            raise _missing_task(task_id)
        raise _api_error(response)

    def list_events(self, task_id: str, *, after: int = 0) -> list[TaskEventCopy]:
        response = self._client.get(
            f"/tasks/{task_id}/events",
            params={"after": after},
        )
        if response.status_code == 200:
            return [TaskEventCopy.model_validate(item) for item in response.json()]
        if response.status_code == 404:
            raise _missing_task(task_id)
        raise _api_error(response)

    def send_message(self, task_id: str, request: TaskMessageRequest) -> MessageReceipt:
        response = self._client.post(
            f"/tasks/{task_id}/messages",
            json=request.model_dump(mode="json"),
        )
        if response.status_code == 200:
            return MessageReceipt.model_validate(response.json())
        if response.status_code == 404:
            raise _missing_task(task_id)
        if response.status_code == 409:
            detail = _response_detail(response)
            raise TaskClientError(status_code=409, detail=detail)
        raise _api_error(response)

    def get_message_receipt(self, task_id: str, message_id: str) -> MessageReceipt:
        response = self._client.get(
            f"/tasks/{task_id}/messages/{message_id}",
        )
        if response.status_code == 200:
            return MessageReceipt.model_validate(response.json())
        if response.status_code == 404:
            raise TaskNotFoundError(
                status_code=404,
                detail=f"task or message not found: {task_id}/{message_id}",
            )
        raise _api_error(response)

    def cancel(self, task_id: str) -> TaskRecord:
        response = self._client.post(f"/tasks/{task_id}/cancel")
        if response.status_code == 200:
            return TaskRecord.model_validate(response.json())
        if response.status_code == 404:
            raise _missing_task(task_id)
        if response.status_code == 409:
            raise TaskClientError(status_code=409, detail=_response_detail(response))
        raise _api_error(response)

    def result(self, task_id: str) -> TaskResultRecord:
        response = self._client.get(f"/tasks/{task_id}/result")
        if response.status_code == 200:
            return TaskResultRecord.model_validate(response.json())
        if response.status_code == 404:
            raise _missing_task(task_id)
        raise _api_error(response)

    def retry(self, task_id: str, request: RetryTaskRequest) -> SubmitResponse:
        response = self._client.post(
            f"/tasks/{task_id}/retry",
            json=request.model_dump(mode="json"),
        )
        if response.status_code in {200, 201}:
            record = TaskRecord.model_validate(response.json())
            return SubmitResponse(record=record, created=response.status_code == 201)
        if response.status_code == 404:
            raise _missing_task(task_id)
        if response.status_code == 409:
            raise TaskClientError(status_code=409, detail=_response_detail(response))
        raise _api_error(response)

    def subscribe_events(
        self, task_id: str, *, after: int = 0
    ) -> TaskEventSubscription:
        return TaskEventSubscription(self, task_id, after_cursor=after)


class TaskEventSubscription:
    """Blocking iterator over one task's copied conversation events."""

    def __init__(
        self,
        client: TaskClient,
        task_id: str,
        *,
        after_cursor: int = 0,
    ) -> None:
        self._client = client
        self._task_id = task_id
        self._connection: ClientConnection | None = None
        self._cursor = after_cursor

    def __enter__(self) -> TaskEventSubscription:
        self._open_connection()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def __iter__(self) -> TaskEventSubscription:
        return self

    @property
    def cursor(self) -> int:
        """Durable cursor safe to pass when reconnecting."""
        return self._cursor

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def __next__(self) -> TaskEventCopy:
        return self.receive()

    def receive(self, *, timeout: float | None = None) -> TaskEventCopy:
        if self._connection is None:
            raise RuntimeError("subscription must be entered before receiving events")
        raw = self._connection.recv(timeout=timeout)
        if isinstance(raw, bytes):
            raw = raw.decode()
        copy = TaskEventCopy.model_validate_json(raw)
        self._cursor = max(self._cursor, copy.cursor)
        return copy

    def reconnect(self) -> None:
        """Open a new socket starting after the latest durable cursor."""
        self.close()
        self._open_connection()

    def _open_connection(self) -> None:
        try:
            self._connection = connect(
                _task_events_websocket_url(
                    self._client.settings.api_url,
                    self._task_id,
                    after=self._cursor,
                ),
                additional_headers={
                    RUNTIME_API_KEY_HEADER: self._client.settings.api_key
                },
                open_timeout=self._client.settings.timeout,
                close_timeout=5,
            )
        except InvalidStatus as exc:
            raise TaskClientError(
                status_code=exc.response.status_code,
                detail=f"event socket rejected: HTTP {exc.response.status_code}",
            ) from exc


def stream_task_events(
    client: TaskClient,
    task_id: str,
    *,
    after: int = 0,
    on_event: Callable[[TaskEventCopy], None],
    poll_timeout: float = 30.0,
) -> int:
    """Deliver backlog and live copies once, skipping duplicates."""
    displayed = after
    for copy in client.list_events(task_id, after=after):
        if copy.cursor <= displayed:
            continue
        on_event(copy)
        displayed = max(displayed, copy.cursor)
    with client.subscribe_events(task_id, after=displayed) as subscription:
        while True:
            copy = subscription.receive(timeout=poll_timeout)
            if copy.cursor <= displayed:
                continue
            on_event(copy)
            displayed = max(displayed, copy.cursor)
    return displayed


def _task_events_websocket_url(api_url: str, task_id: str, *, after: int) -> str:
    parsed = urlsplit(api_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    path = f"{parsed.path.rstrip('/')}/tasks/sockets/events/{task_id}"
    query = f"after={after}" if after else ""
    return urlunsplit((scheme, parsed.netloc, path, query, ""))


def _response_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except json.JSONDecodeError:
        return response.text or response.reason_phrase
    if isinstance(payload, dict) and "detail" in payload:
        detail = payload["detail"]
        if isinstance(detail, str):
            return detail
        return json.dumps(detail)
    return json.dumps(payload)


def _api_error(response: httpx.Response) -> TaskClientError:
    detail = _response_detail(response)
    if response.status_code == 404:
        return TaskNotFoundError(status_code=404, detail=detail)
    return TaskClientError(status_code=response.status_code, detail=detail)


__all__ = [
    "SubmitResponse",
    "TaskClient",
    "TaskClientError",
    "TaskEventSubscription",
    "TaskNotFoundError",
    "stream_task_events",
]
