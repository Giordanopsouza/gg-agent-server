"""Metadata-only telemetry for the sandbox server and Pi RPC bridge."""

from __future__ import annotations

import re
import sys
from collections.abc import Callable
from contextvars import ContextVar
from uuid import UUID

import logfire
from fastapi import FastAPI, Request, Response
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from gg.server.config import Settings


task_context: ContextVar[tuple[str, str] | None] = ContextVar(
    "gg_logfire_task_context", default=None
)
_sqlite_enabled = False


def trace_sqlite_query[T](sql: str, execute: Callable[[], T]) -> T:
    """Measure one query by call site without exporting SQL or bound values."""
    if not _sqlite_enabled or not trace.get_current_span().is_recording():
        return execute()
    first = sql.lstrip().split(None, 1)
    operation = first[0].upper() if first else "OTHER"
    if operation not in {
        "SELECT",
        "INSERT",
        "UPDATE",
        "DELETE",
        "REPLACE",
        "PRAGMA",
        "BEGIN",
        "COMMIT",
        "ROLLBACK",
        "CREATE",
        "ALTER",
        "DROP",
        "WITH",
    }:
        operation = "OTHER"
    caller = sys._getframe(2)
    module = caller.f_globals.get("__name__", "unknown")
    if operation == "PRAGMA":
        return execute()
    location = f"{module}:{caller.f_lineno}"
    failure: BaseException | None = None
    result: T | None = None
    with logfire.span(
        "sqlite query", db_operation=operation, code_location=location
    ) as span:
        try:
            result = execute()
        except BaseException as exc:
            span.set_attribute("error_type", type(exc).__name__)
            failure = exc
    if failure is not None:
        raise failure.with_traceback(failure.__traceback__)
    return result  # type: ignore[return-value]


def configure_server_observability(settings: Settings) -> None:
    if not settings.logfire_enabled:
        return
    if not settings.logfire_relay_url or not settings.logfire_task_id:
        raise ValueError("sandbox Logfire relay URL and task ID are required")
    if len(settings.session_api_keys) != 1:
        raise ValueError("sandbox Logfire relay requires one session API key")
    exporter = OTLPSpanExporter(
        endpoint=settings.logfire_relay_url.rstrip("/") + "/v1/traces",
        headers={
            "X-GG-Task-ID": settings.logfire_task_id,
            "X-Session-API-Key": settings.session_api_keys[0],
        },
        timeout=5,
    )
    logfire.configure(
        send_to_logfire=False,
        service_name="gg-server",
        environment=settings.logfire_environment,
        console=False,
        inspect_arguments=False,
        distributed_tracing=True,
        sampling=logfire.SamplingOptions(head=settings.logfire_sample_rate),
        additional_span_processors=[BatchSpanProcessor(exporter)],
        metrics=False,
    )
    global _sqlite_enabled
    _sqlite_enabled = True


def instrument_server_http(app: FastAPI) -> None:
    """Keep request content, URLs, headers, and exception messages out of spans."""

    @app.middleware("http")
    async def trace_request(request: Request, call_next) -> Response:
        path = request.url.path
        polling = request.method == "GET" and re.fullmatch(
            r"/api/task-executions/[0-9a-fA-F-]{36}(?:/manifest)?", path
        )
        if path in {"/health", "/ready"} or polling:
            return await call_next(request)
        carrier = {
            name: request.headers[name]
            for name in ("traceparent", "tracestate")
            if name in request.headers
        }
        error: Exception | None = None
        response: Response | None = None
        with logfire.attach_context(carrier):
            with logfire.span(
                "server HTTP request", http_method=request.method
            ) as span:
                try:
                    response = await call_next(request)
                    span.set_attribute("http_status_code", response.status_code)
                except Exception as exc:
                    span.set_attribute("error_type", type(exc).__name__)
                    error = exc
                route = request.scope.get("route")
                if route is not None:
                    span.set_attribute("http_route", route.path)
                path_params = request.scope.get("path_params") or {}
                execution_id = path_params.get("execution_id")
                if isinstance(execution_id, str):
                    try:
                        if str(UUID(execution_id)) == execution_id:
                            span.set_attribute("task_id", execution_id)
                    except ValueError:
                        pass
        if error is not None:
            raise error
        assert response is not None
        return response
