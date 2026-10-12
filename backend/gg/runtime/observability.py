"""Optional, metadata-only runtime telemetry.

Automatic web instrumentation records query strings and endpoint arguments,
which can contain OAuth codes or task prompts. Keep the HTTP boundary explicit.
"""

from __future__ import annotations

import sys
from collections.abc import Awaitable, Callable

import logfire
from fastapi import FastAPI, Request, Response

from gg.runtime.config import RuntimeSettings


_sqlite_enabled = False


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
    location = f"{caller.f_globals.get('__name__', 'unknown')}:{caller.f_lineno}"
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
    global _sqlite_enabled
    _sqlite_enabled = True


def instrument_runtime_http(app: FastAPI) -> None:
    """Record only method, matched route, status, and duration."""

    @app.middleware("http")
    async def trace_request(request: Request, call_next) -> Response:
        if request.url.path in {"/health", "/ready"}:
            return await call_next(request)

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
