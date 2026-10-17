"""Sandbox tracing accepts context and exports only safe HTTP metadata."""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace

import httpx
import logfire
import pytest
from fastapi import FastAPI, Response
from httpx import ASGITransport
from logfire.testing import CaptureLogfire

from gg.server import observability
from gg.server.config import _load_settings, publication_process_env
from gg.server.observability import instrument_server_http
from gg.server.sqlite_state import ObservedConnection


@pytest.mark.anyio
async def test_server_http_trace_propagates_parent_without_request_content(
    capfire: CaptureLogfire,
) -> None:
    app = FastAPI()

    @app.get("/tasks/{task_id}")
    def task(task_id: str) -> dict[str, str]:
        return {"task_id": task_id}

    @app.get("/api/task-executions/{execution_id}")
    def polling(execution_id: str) -> dict[str, str]:
        return {"execution_id": execution_id}

    instrument_server_http(app)
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://sandbox"
    ) as client:
        with logfire.span("runtime request"):
            headers = logfire.get_context()
            headers["Authorization"] = "Bearer private-header"
            response = await client.get(
                "/tasks/private-path?code=private-query", headers=headers
            )
            polled = await client.get(
                "/api/task-executions/632925df-0f19-4309-ad2d-5ba915ad6348",
                headers=headers,
            )

    assert response.status_code == 200
    assert polled.status_code == 200
    spans = capfire.exporter.exported_spans_as_dict()
    parent = next(span for span in spans if span["name"] == "runtime request")
    child = next(span for span in spans if span["name"] == "server HTTP request")
    assert sum(span["name"] == "server HTTP request" for span in spans) == 1
    assert child["context"]["trace_id"] == parent["context"]["trace_id"]
    assert child["attributes"]["http_route"] == "/tasks/{task_id}"
    assert child["attributes"]["http_status_code"] == 200
    for secret in ("private-path", "private-query", "private-header"):
        assert secret not in repr(spans)


def test_logfire_settings_and_subprocess_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GG_LOGFIRE_ENABLED", "TRUE")
    monkeypatch.setenv("GG_LOGFIRE_SAMPLE_RATE", "0.25")
    monkeypatch.setenv("LOGFIRE_TOKEN", "private-logfire-token")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_HEADERS", "private-headers")

    settings = _load_settings()

    assert settings.logfire_enabled is True
    assert settings.logfire_sample_rate == 0.25
    assert "LOGFIRE_TOKEN" not in settings.process_env
    assert "OTEL_EXPORTER_OTLP_HEADERS" not in settings.process_env
    assert "LOGFIRE_TOKEN" not in publication_process_env()
    assert "OTEL_EXPORTER_OTLP_HEADERS" not in publication_process_env()


def test_sandbox_sqlite_queries_omit_statement_and_values(
    capfire: CaptureLogfire, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("gg.server.observability._sqlite_enabled", True)
    monkeypatch.setattr(observability, "time", SimpleNamespace(perf_counter=lambda: 0))
    connection = sqlite3.connect(":memory:", factory=ObservedConnection)
    try:
        connection.execute("PRAGMA user_version")
        with logfire.span("task query"):
            connection.execute("CREATE TABLE items (value TEXT)")
            connection.execute("INSERT INTO items VALUES (?)", ("private-value",))
    finally:
        connection.close()

    spans = [
        span
        for span in capfire.exporter.exported_spans_as_dict()
        if span["name"].startswith("sqlite query")
    ]
    assert spans == []
    assert "private-value" not in repr(spans)
    assert "INSERT INTO items" not in repr(spans)


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
    path = "/api/conversations/632925df-0f19-4309-ad2d-5ba915ad6348/events"

    @app.get(path)
    async def polling():
        if outcome == "exception":
            raise ValueError("private-error")
        return Response(status_code=503 if outcome == "failure" else 200)

    instrument_server_http(app)
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


def test_sqlite_failure_keeps_only_error_type(
    capfire: CaptureLogfire,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(observability, "_sqlite_enabled", True)
    connection = sqlite3.connect(":memory:", factory=ObservedConnection)
    try:
        with pytest.raises(sqlite3.OperationalError):
            connection.execute("SELECT private_value FROM private_table")
    finally:
        connection.close()
    records = capfire.exporter.exported_spans_as_dict()
    assert len(records) == 1
    assert records[0]["name"] == "sqlite query failed"
    assert records[0]["attributes"]["error_type"] == "OperationalError"
    assert "private_value" not in repr(records)
    assert "private_table" not in repr(records)
