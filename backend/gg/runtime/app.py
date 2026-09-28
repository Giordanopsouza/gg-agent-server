"""FastAPI control plane for Modal background tasks."""

from __future__ import annotations

import os
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Request,
    Response,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader

from gg.runtime.config import RuntimeSettings
from gg.runtime.github import HttpGitHubGateway
from gg.runtime.github_connection import (
    GitHubClient,
    PostgresGitHubConnections,
    github_connection_router,
)
from gg.runtime.ledger import TaskLedger
from gg.runtime.modal_sandbox import ModalSandboxLifecycle, lifecycle_from_settings
from gg.runtime.openrouter_vault import (
    OpenRouterKeyVerifier,
    PostgresOpenRouterVault,
    openrouter_vault_router,
)
from gg.runtime.postgres import RuntimePostgres
from gg.runtime.publication import BotIdentity, DraftPublisher
from gg.runtime.readiness import readiness_from_scheduler
from gg.runtime.repository_authorization import RepositoryAuthorization
from gg.runtime.scheduler import TaskScheduler, default_lock_path
from gg.runtime.storage import StorageLimits
from gg.runtime.task_auth import task_access
from gg.runtime.task_routes import event_socket_router, router as task_router
from gg.runtime.task_service import TaskService
from gg.runtime.task_supervision.manager import TaskSupervisionManager
from gg.runtime.web_auth import SupabaseAuth, web_auth_router
from gg.runtime.web_sessions import PostgresWebSessions


_CONTROL_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def _check_api_key(
    request: Request,
    api_key: str | None = Depends(_CONTROL_API_KEY_HEADER),
) -> None:
    settings: RuntimeSettings = request.app.state.settings
    if not secrets.compare_digest(api_key or "", settings.api_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)


def create_app(
    settings: RuntimeSettings,
    *,
    task_ledger: TaskLedger | None = None,
    modal_lifecycle: ModalSandboxLifecycle | None = None,
    task_scheduler: TaskScheduler | None = None,
    task_supervision: TaskSupervisionManager | None = None,
    web_auth: SupabaseAuth | None = None,
    web_sessions: PostgresWebSessions | None = None,
    openrouter_vault: PostgresOpenRouterVault | None = None,
    openrouter_verifier: OpenRouterKeyVerifier | None = None,
    github_connections: PostgresGitHubConnections | None = None,
    github_client: GitHubClient | None = None,
    repository_authorization: RepositoryAuthorization | None = None,
) -> FastAPI:
    """Build the standalone runtime app."""
    database_url = os.getenv("GG_RUNTIME_DATABASE_URL")
    if task_ledger is not None:
        ledger = task_ledger
    elif database_url:
        ledger = TaskLedger(RuntimePostgres.from_env())
    else:
        raise RuntimeError("GG_RUNTIME_DATABASE_URL is required for the runtime")
    ledger.open()
    web_engine = None
    if (
        web_sessions is None
        and settings.supabase_url
        and os.getenv("GG_RUNTIME_DATABASE_URL")
    ):
        web_engine = ledger.engine
        web_sessions = PostgresWebSessions(web_engine)
    if (
        openrouter_vault is None
        and web_engine is not None
        and settings.openrouter_vault_key
    ):
        openrouter_vault = PostgresOpenRouterVault(
            web_engine, settings.openrouter_vault_key
        )

    if (
        github_connections is None
        and web_engine is not None
        and settings.github_connection_key
    ):
        github_connections = PostgresGitHubConnections(
            web_engine, settings.github_connection_key
        )
    github_client = github_client or GitHubClient(settings)
    if (
        repository_authorization is None
        and github_connections is not None
        and settings.github_app_client_id
    ):
        repository_authorization = RepositoryAuthorization(
            github_connections,
            client_id=settings.github_app_client_id,
            private_key=settings.github_app_private_key,
        )
    openrouter_verifier = openrouter_verifier or OpenRouterKeyVerifier()
    task_service = TaskService(
        ledger=ledger,
        settings=settings,
        repository_authorization=repository_authorization,
    )
    lifecycle = modal_lifecycle or lifecycle_from_settings(
        ledger=ledger,
        settings=settings,
        credential_vault=openrouter_vault,
        credential_verifier=openrouter_verifier,
        repository_authorization=repository_authorization,
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
        repository_authorization=repository_authorization,
    )
    storage_limits = StorageLimits.from_settings(settings)
    scheduler = task_scheduler or TaskScheduler(
        ledger=ledger,
        lifecycle=lifecycle,
        capacity=settings.task_capacity,
        lock_path=settings.dispatch_lock_path
        or default_lock_path(deployment=settings.modal_deployment),
        admission_enabled=settings.task_dispatch_enabled,
        poll_seconds=settings.dispatch_poll_seconds,
        supervision=supervision,
        storage_limits=storage_limits,
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
    app.state.repository_authorization = repository_authorization
    app.state.task_scheduler = scheduler
    app.state.task_supervision = supervision
    app.state.storage_limits = storage_limits
    app.state.web_auth = web_auth or SupabaseAuth(settings)
    app.state.web_sessions = web_sessions

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

    app.include_router(task_router, dependencies=[Depends(task_access)])
    app.include_router(web_auth_router(settings, app.state.web_auth, web_sessions))
    app.include_router(
        openrouter_vault_router(
            settings,
            app.state.web_auth,
            web_sessions,
            openrouter_vault,
            openrouter_verifier,
        )
    )
    app.include_router(
        github_connection_router(
            settings,
            app.state.web_auth,
            web_sessions,
            github_connections,
            github_client,
        )
    )
    app.include_router(event_socket_router)

    return app
