"""Optional, metadata-only runtime telemetry.

Automatic web instrumentation records query strings and endpoint arguments,
which can contain OAuth codes or task prompts. Keep the HTTP boundary explicit.
"""

from __future__ import annotations

import re
import sys
import time
from collections.abc import Awaitable, Callable

import logfire
from fastapi import FastAPI, Request, Response

from gg.runtime.config import RuntimeSettings


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
    if module in {"gg.runtime.sqlite_db", "gg.runtime.sqlite_migrations"}:
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


async def trace_task_call[T](
    operation: str,
    task_id: str,
    call: Callable[[], Awaitable[T]],
    *,
    enabled: bool,
) -> T:
    """Trace a task step without exporting exception messages or arguments."""
    if not enabled:
        return await call()

    failure: BaseException | None = None
    with logfire.span(operation, task_id=task_id) as span:
        try:
            return await call()
        except BaseException as exc:
            span.set_attribute("error_type", type(exc).__name__)
            failure = exc
    assert failure is not None
    raise failure.with_traceback(failure.__traceback__)


def configure_runtime_observability(settings: RuntimeSettings) -> None:
    """Configure Logfire once, before the app opens its database connections."""
    if not settings.logfire_enabled:
        return
    logfire.configure(
        send_to_logfire="if-token-present",
        service_name="gg-runtime",
        environment=settings.logfire_environment,
        console=False,
        inspect_arguments=False,
        distributed_tracing=False,
        sampling=logfire.SamplingOptions(head=settings.logfire_sample_rate),
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


def instrument_runtime_http(app: FastAPI) -> None:
    """Record only method, matched route, status, and duration."""

    @app.middleware("http")
    async def trace_request(request: Request, call_next) -> Response:
        path = request.url.path
        polling = request.method == "GET" and (
            path in {"/auth/session", "/tasks", "/tasks/dispatch/status"}
            or re.fullmatch(r"/tasks/[0-9a-fA-F-]{36}(?:/(?:events|result))?", path)
            is not None
        )
        if (
            path in {"/health", "/ready"}
            or path.startswith("/internal/logfire/")
            or polling
        ):
            return await _trace_quiet_request(request, call_next)

        error: Exception | None = None
        response: Response | None = None
        with logfire.span("runtime HTTP request", http_method=request.method) as span:
            try:
                response = await call_next(request)
                span.set_attribute("http_status_code", response.status_code)
            except Exception as exc:
                # Exception messages may contain request data or provider URLs.
                span.set_attribute("error_type", type(exc).__name__)
                error = exc
            route = request.scope.get("route")
            if route is not None:
                span.set_attribute("http_route", route.path)
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
