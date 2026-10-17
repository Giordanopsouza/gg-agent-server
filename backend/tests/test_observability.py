"""Metadata-only HTTP tracing must not export request contents."""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import logfire
import pytest
from fastapi import FastAPI, Response
from httpx import ASGITransport
from logfire.testing import CaptureLogfire

from gg.runtime import RuntimeSettings, create_app, observability
from gg.runtime.modal_sandbox import SandboxConnection
from gg.runtime.observability import instrument_runtime_http, trace_task_call
from gg.runtime.sqlite_db import ObservedConnection
from test_support.sqlite_ledger import new_ledger


@pytest.mark.anyio
async def test_runtime_http_trace_keeps_only_route_status_and_method(
    capfire: CaptureLogfire,
) -> None:
    app = FastAPI()

    @app.get("/items/{item_id}")
    def item(item_id: str) -> dict[str, str]:
        return {"item_id": item_id}

    @app.get("/tasks")
    def polling() -> dict[str, str]:
        return {"status": "ok"}

    instrument_runtime_http(app)
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/items/private-path?code=private-query",
            headers={"Authorization": "Bearer private-header"},
        )
        polled = await client.get("/tasks")

    assert response.status_code == 200
    assert polled.status_code == 200
    spans = capfire.exporter.exported_spans_as_dict()
    request_span = next(
        span for span in spans if span["name"] == "runtime HTTP request"
    )
    assert sum(span["name"] == "runtime HTTP request" for span in spans) == 1
    assert request_span["attributes"]["http_method"] == "GET"
    assert request_span["attributes"]["http_route"] == "/items/{item_id}"
    assert request_span["attributes"]["http_status_code"] == 200
    exported = repr(spans)
    for secret in ("private-path", "private-query", "private-header"):
        assert secret not in exported


@pytest.mark.anyio
async def test_task_span_records_id_and_failure_type_without_exception_text(
    capfire: CaptureLogfire,
) -> None:
    async def fail() -> None:
        raise ValueError("private-error-text")

    with pytest.raises(ValueError, match="private-error-text"):
        await trace_task_call(
            "runtime sandbox creation", "task-123", fail, enabled=True
        )

    spans = capfire.exporter.exported_spans_as_dict()
    task_span = next(
        span for span in spans if span["name"] == "runtime sandbox creation"
    )
    assert task_span["attributes"]["task_id"] == "task-123"
    assert task_span["attributes"]["error_type"] == "ValueError"
    assert "private-error-text" not in repr(spans)


def test_sandbox_headers_propagate_trace_without_exporting_credentials(
    capfire: CaptureLogfire,
) -> None:
    connection = SandboxConnection(
        "https://sandbox.example", "connect-secret", "api-secret"
    )
    with logfire.span("runtime dispatch", task_id="task-123"):
        headers = connection._headers()

    assert headers["Authorization"] == "Bearer connect-secret"
    assert headers["X-Session-API-Key"] == "api-secret"
    assert headers["traceparent"].startswith("00-")
    assert "connect-secret" not in repr(capfire.exporter.exported_spans_as_dict())


def test_sqlite_query_trace_omits_statement_and_values(
    capfire: CaptureLogfire, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("gg.runtime.observability._sqlite_enabled", True)
    monkeypatch.setattr(observability, "time", SimpleNamespace(perf_counter=lambda: 0))
    connection = sqlite3.connect(":memory:", factory=ObservedConnection)
    try:
        connection.execute("PRAGMA user_version")
        with logfire.span("task query"):
            connection.execute("CREATE TABLE items (value TEXT)")
            connection.execute("INSERT INTO items VALUES (?)", ("private-value",))
            with pytest.raises(sqlite3.Error):
                connection.execute("SELECT private-literal FROM missing_table")
    finally:
        connection.close()

    spans = [
        span
        for span in capfire.exporter.exported_spans_as_dict()
        if span["name"].startswith("sqlite query")
    ]
    assert [span["attributes"]["db_operation"] for span in spans] == [
        "SELECT",
    ]
    assert spans[-1]["name"] == "sqlite query failed"
    assert spans[-1]["attributes"]["error_type"] == "OperationalError"
    assert all("code_location" in span["attributes"] for span in spans)
    exported = repr(spans)
    assert "private-value" not in exported
    assert "private-literal" not in exported


@pytest.mark.anyio
async def test_logfire_relay_requires_task_session_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = new_ledger()
    ledger.open()
    task, _ = ledger.submit(
        idempotency_key="relay-task",
        repository="owner/repo",
        prompt="private-prompt",
        base_ref=None,
        retry_of=None,
    )
    ledger.begin_sandbox_creation(
        task_id=task.id,
        deployment="production",
        sandbox_name="relay-sandbox",
        tags_json="{}",
        session_api_key="private-session-key",
    )
    forward = AsyncMock(return_value=Response(status_code=202))
    monkeypatch.setattr(logfire, "forward_export_request_starlette", forward)
    app = create_app(
        RuntimeSettings(
            api_key="control",
            logfire_enabled=True,
            logfire_relay_url="http://test/internal/logfire",
        ),
        task_ledger=ledger,
    )
    app.state.recovering = False
    headers = {"X-GG-Task-ID": task.id, "Content-Type": "application/x-protobuf"}
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        denied = await client.post(
            "/internal/logfire/v1/traces", headers=headers, content=b"data"
        )
        headers["X-Session-API-Key"] = "private-session-key"
        accepted = await client.post(
            "/internal/logfire/v1/traces", headers=headers, content=b"data"
        )
    assert denied.status_code == 401
    assert accepted.status_code == 202
    assert forward.await_count == 1
    ledger.close()


def test_sqlite_slow_query_is_kept_without_active_request(
    capfire: CaptureLogfire,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(observability, "_sqlite_enabled", True)
    ticks = iter((0.0, 0.2))
    monkeypatch.setattr(
        observability, "time", SimpleNamespace(perf_counter=lambda: next(ticks))
    )
    connection = sqlite3.connect(":memory:", factory=ObservedConnection)
    try:
        assert connection.execute("SELECT 42").fetchone() == (42,)
    finally:
        connection.close()
    records = capfire.exporter.exported_spans_as_dict()
    assert len(records) == 1
    assert records[0]["name"] == "sqlite query slow"
    assert records[0]["attributes"]["duration_ms"] == 200
    assert "SELECT 42" not in repr(records)


@pytest.mark.anyio
@pytest.mark.parametrize("outcome", ["success", "failure", "slow", "exception"])
async def test_polling_preserves_abnormal_requests_only(
    capfire: CaptureLogfire,
    monkeypatch: pytest.MonkeyPatch,
    outcome: str,
) -> None:
    app = FastAPI()
    ticks = iter((0.0, 2.0 if outcome == "slow" else 0.01))
    monkeypatch.setattr(
        observability, "time", SimpleNamespace(perf_counter=lambda: next(ticks))
    )
    path = "/tasks"

    @app.get(path)
    async def polling():
        if outcome == "exception":
            raise ValueError("private-error")
        return Response(status_code=503 if outcome == "failure" else 200)

    instrument_runtime_http(app)
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        if outcome == "exception":
            with pytest.raises(ValueError, match="private-error"):
                await client.get(path + "?secret=private-query")
        else:
            response = await client.get(path + "?secret=private-query")
            assert response.status_code == (503 if outcome == "failure" else 200)
    records = capfire.exporter.exported_spans_as_dict()
    assert len(records) == (0 if outcome == "success" else 1)
    if records:
        assert records[0]["attributes"]["http_route"] == path
    assert "private-error" not in repr(records)
    assert "private-query" not in repr(records)


def test_framework_scopes_are_suppressed_but_task_spans_remain(
    capfire: CaptureLogfire,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from opentelemetry import trace

    monkeypatch.setattr(logfire, "configure", lambda **kwargs: None)
    observability.configure_runtime_observability(
        RuntimeSettings(api_key="test-control", logfire_enabled=True)
    )
    for scope in ("fastapi", "opentelemetry.instrumentation.asgi"):
        with trace.get_tracer(scope).start_as_current_span("framework detail"):
            pass
    with logfire.span("runtime sandbox creation", task_id="task-123"):
        pass
    records = capfire.exporter.exported_spans_as_dict()
    assert [record["name"] for record in records] == ["runtime sandbox creation"]
