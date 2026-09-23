"""FastAPI control plane for Modal background tasks."""

from __future__ import annotations

import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Request,
    Response,
    WebSocket,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader

from gg.runtime.config import RuntimeSettings
from gg.runtime.github import HttpGitHubGateway
from gg.runtime.ledger import TaskLedger
from gg.runtime.modal_sandbox import ModalSandboxLifecycle, lifecycle_from_settings
from gg.runtime.publication import BotIdentity, DraftPublisher
from gg.runtime.readiness import readiness_from_scheduler
from gg.runtime.scheduler import TaskScheduler, default_lock_path
from gg.runtime.storage import StorageLimits
from gg.runtime.task_routes import event_socket_router, router as task_router
from gg.runtime.task_service import TaskService
from gg.runtime.task_supervision.manager import TaskSupervisionManager


_CONTROL_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def _check_api_key(
    request: Request,
    api_key: str | None = Depends(_CONTROL_API_KEY_HEADER),
) -> None:
    settings: RuntimeSettings = request.app.state.settings
    if not secrets.compare_digest(api_key or "", settings.api_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)


def _check_socket_api_key(websocket: WebSocket) -> None:
    """Authenticate a task event socket from handshake headers, not Request."""

    settings: RuntimeSettings = websocket.app.state.settings
    provided = websocket.headers.get("x-api-key") or ""
    if not secrets.compare_digest(provided, settings.api_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)


def create_app(
    settings: RuntimeSettings,
    *,
    task_ledger: TaskLedger | None = None,
    modal_lifecycle: ModalSandboxLifecycle | None = None,
    task_scheduler: TaskScheduler | None = None,
    task_supervision: TaskSupervisionManager | None = None,
) -> FastAPI:
    """Build the standalone runtime app."""
    ledger = task_ledger or TaskLedger(db_path=settings.task_db_path)
    ledger.open()
    task_service = TaskService(ledger=ledger, settings=settings)
    lifecycle = modal_lifecycle or lifecycle_from_settings(
        ledger=ledger, settings=settings
    )
    publisher = None
    if settings.github_clone_token:
        publisher = DraftPublisher(
            ledger=ledger,
            github=HttpGitHubGateway(token=settings.github_clone_token),
            bot=BotIdentity(
                name="gg-bot",
                email="gg-bot@users.noreply.github.com",
                login="gg-bot",
            ),
            github_token=settings.github_clone_token,
        )
    supervision = task_supervision or TaskSupervisionManager(
        ledger=ledger,
        lifecycle=lifecycle,
        settings=settings,
        publisher=publisher,
    )
    storage_limits = StorageLimits.from_settings(settings)
    scheduler = task_scheduler or TaskScheduler(
        ledger=ledger,
        lifecycle=lifecycle,
        capacity=settings.task_capacity,
        lock_path=settings.dispatch_lock_path
        or default_lock_path(
            db_path=settings.task_db_path,
            deployment=settings.modal_deployment,
        ),
        admission_enabled=settings.task_dispatch_enabled,
        poll_seconds=settings.dispatch_poll_seconds,
        supervision=supervision,
        storage_limits=storage_limits,
        task_db_path=settings.task_db_path,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        scheduler_started = False
        try:
            await supervision.startup()
            await scheduler.start()
            scheduler_started = True
            yield
        finally:
            if scheduler_started:
                await scheduler.stop()
            await supervision.shutdown()
            ledger.close()

    app = FastAPI(title="gg-runtime", lifespan=lifespan)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_methods=["GET", "POST"],
            allow_headers=["X-API-Key", "Content-Type"],
        )
    app.state.settings = settings
    app.state.task_ledger = ledger
    app.state.task_service = task_service
    app.state.task_scheduler = scheduler
    app.state.task_supervision = supervision
    app.state.storage_limits = storage_limits

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get(
        "/ready",
        dependencies=[Depends(_check_api_key)],
    )
    def ready(
        response: Response,
        request: Request,
    ) -> dict[str, object]:
        scheduler: TaskScheduler = request.app.state.task_scheduler
        ledger: TaskLedger = request.app.state.task_ledger
        report = readiness_from_scheduler(
            scheduler,
            database_available=ledger.ping_database(),
        )
        if report.status != "ready":
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return report.model_dump(mode="json")

    app.include_router(task_router, dependencies=[Depends(_check_api_key)])
    app.include_router(
        event_socket_router, dependencies=[Depends(_check_socket_api_key)]
    )

    return app
