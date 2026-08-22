"""FastAPI application factory and health routes."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response

from gg.server.config import Settings


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Run startup work, then mark the app ready for traffic."""
    ready_event: asyncio.Event = app.state.ready_event
    ready_event.set()
    try:
        yield
    finally:
        ready_event.clear()


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

    return app
