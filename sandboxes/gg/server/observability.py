"""Metadata-only telemetry for the sandbox server and Pi RPC bridge."""

from __future__ import annotations

import re
import sys
import time
from collections.abc import Callable
from contextvars import ContextVar
from uuid import UUID

import logfire
from fastapi import FastAPI, Request, Response
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from gg.server.config import Settings


task_context: ContextVar[tuple[str, str] | None] = ContextVar(
    "gg_logfire_task_context", default=None
)
_sqlite_enabled = False
SQLITE_SLOW_SECONDS = 0.1
HTTP_SLOW_SECONDS = 1.0


def trace_sqlite_query[T](sql: str, execute: Callable[[], T]) -> T:
    """Measure one query by call site without exporting SQL or bound values."""
    if not _sqlite_enabled:
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
    started = time.perf_counter()
    try:
        result = execute()
    except BaseException as exc:
        logfire.error(
            "sqlite query failed",
            db_operation=operation,
            code_location=location,
            duration_ms=(time.perf_counter() - started) * 1000,
            error_type=type(exc).__name__,
        )
        raise
    duration = time.perf_counter() - started
    if duration >= SQLITE_SLOW_SECONDS:
        logfire.warn(
            "sqlite query slow",
            db_operation=operation,
            code_location=location,
            duration_ms=duration * 1000,
        )
    return result


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
    # Some launchers auto-instrument FastAPI. Our explicit HTTP boundary below
    # owns operational errors without framework internals or request contents.
    logfire.suppress_scopes(
        "fastapi",
        "opentelemetry.instrumentation.fastapi",
        "opentelemetry.instrumentation.asgi",
    )
    global _sqlite_enabled
    _sqlite_enabled = True


def instrument_server_http(app: FastAPI) -> None:
    """Keep request content, URLs, headers, and exception messages out of spans."""

    @app.middleware("http")
    async def trace_request(request: Request, call_next) -> Response:
        path = request.url.path
        polling = request.method == "GET" and re.fullmatch(
            r"/(?:api/)?(?:task-executions/[0-9a-fA-F-]{36}(?:/manifest)?"
            r"|conversations/[0-9a-fA-F-]{36}/events)",
            path,
        )
        if path in {"/health", "/ready"} or polling:
            return await _trace_quiet_request(request, call_next)
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


async def _trace_quiet_request(request: Request, call_next) -> Response:
    """Keep only failures and slow responses for repetitive internal traffic."""
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:
        route = request.scope.get("route")
        logfire.error(
            "HTTP background request failed",
            http_method=request.method,
            http_route=route.path if route is not None else None,
            error_type=type(exc).__name__,
            duration_ms=(time.perf_counter() - started) * 1000,
        )
        raise
    duration = time.perf_counter() - started
    if response.status_code >= 400 or duration >= HTTP_SLOW_SECONDS:
        route = request.scope.get("route")
        logfire.log(
            "error" if response.status_code >= 500 else "warn",
            "HTTP background request abnormal",
            attributes={
                "http_method": request.method,
                "http_route": route.path if route is not None else None,
                "http_status_code": response.status_code,
                "duration_ms": duration * 1000,
            },
        )
    return response
