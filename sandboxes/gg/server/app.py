"""FastAPI application factory and health routes."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from gg.server.api import api_router
from gg.server.config import Settings
from gg.server.conversation_service import ConversationService
from gg.server.dependencies import check_session_api_key
from gg.server.task_supervisor.service import TaskSupervisorService
from gg.server.websocket_routes import event_socket_router


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Run startup work, then mark the app ready for traffic."""
    settings: Settings = app.state.settings
    conversation_service = ConversationService(settings)
    task_supervisor = TaskSupervisorService(
        settings=settings,
        conversation_service=conversation_service,
    )
    app.state.conversation_service = conversation_service
    app.state.task_supervisor_service = task_supervisor
    await task_supervisor.startup()
    ready_event: asyncio.Event = app.state.ready_event
    ready_event.set()
    try:
        yield
    finally:
        ready_event.clear()
        await task_supervisor.shutdown()
        app.state.task_supervisor_service = None
        app.state.conversation_service = None


def create_app(settings: Settings) -> FastAPI:
    """Build a FastAPI app wired to the given settings.

    Tests and production both call this factory. There is no module-level app
    instance — that keeps imports side-effect free.
    """
    app = FastAPI(
        title="gg-agent-server",
        description="HTTP server for remote gg agent conversations",
        lifespan=_lifespan,
    )
    app.state.settings = settings
    app.state.ready_event = asyncio.Event()

    @app.exception_handler(RequestValidationError)
    async def validation_error(
        _: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        """Expose malformed API configuration as 400 without echoing inputs."""
        detail = [
            {key: error[key] for key in ("loc", "msg", "type")}
            for error in exc.errors()
        ]
        return JSONResponse(status_code=400, content={"detail": detail})

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Liveness probe: the process is up and serving HTTP."""
        return {"status": "ok"}

    @app.get("/ready")
    async def ready(response: Response) -> dict[str, str]:
        """Readiness probe: startup finished and the API can accept traffic."""
        if app.state.ready_event.is_set():
            return {"status": "ready"}
        response.status_code = 503
        return {"status": "initializing"}

    app.include_router(
        api_router,
        dependencies=[Depends(check_session_api_key)],
    )
    app.include_router(event_socket_router)

    return app
