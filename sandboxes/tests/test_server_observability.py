"""Sandbox tracing accepts context and exports only safe HTTP metadata."""

from __future__ import annotations

import sqlite3

import httpx
import logfire
import pytest
from fastapi import FastAPI
from httpx import ASGITransport
from logfire.testing import CaptureLogfire

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

    assert response.status_code == 200
    spans = capfire.exporter.exported_spans_as_dict()
    parent = next(span for span in spans if span["name"] == "runtime request")
    child = next(span for span in spans if span["name"] == "server HTTP request")
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
        if span["name"] == "sqlite query"
    ]
    assert [span["attributes"]["db_operation"] for span in spans] == [
        "CREATE",
        "INSERT",
    ]
    assert "private-value" not in repr(spans)
    assert "INSERT INTO items" not in repr(spans)
