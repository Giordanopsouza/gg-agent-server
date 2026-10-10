"""FastAPI control plane, sharing one SQLite database and checkpoint owner."""

from __future__ import annotations

import asyncio
import os
import re
import secrets
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader

from gg.runtime.checkpoints import CheckpointCoordinator
from gg.runtime.config import RuntimeSettings
from gg.runtime.github_connection import (
    GitHubClient,
    SQLiteGitHubConnections,
    github_connection_router,
)
from gg.runtime.google_auth import GoogleAuth, google_auth_router
from gg.runtime.ledger import TaskLedger
from gg.runtime.local_sessions import LocalSessions, durable
from gg.runtime.modal_sandbox import ModalSandboxLifecycle, lifecycle_from_settings
from gg.runtime.openrouter_vault import (
    OpenRouterKeyVerifier,
    SQLiteOpenRouterVault,
    openrouter_vault_router,
)
from gg.runtime.readiness import readiness_from_scheduler
from gg.runtime.repository_authorization import RepositoryAuthorization
from gg.runtime.scheduler import TaskScheduler, default_lock_path
from gg.runtime.sqlite_db import SQLiteDB
from gg.runtime.static_web import OriginGuard, StaticWeb
from gg.runtime.storage import StorageLimits
from gg.runtime.task_auth import task_access
from gg.runtime.task_routes import event_socket_router, router as task_router
from gg.runtime.task_service import TaskService
from gg.runtime.task_supervision.manager import TaskSupervisionManager


_CONTROL_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def _check_api_key(
    request: Request, api_key: str | None = Depends(_CONTROL_API_KEY_HEADER)
):
    if not secrets.compare_digest(api_key or "", request.app.state.settings.api_key):
        raise HTTPException(status_code=401)


async def local_commit():
    """Local snapshots are fsynced. Modal wiring supplies Volume.commit.aio."""


def create_app(
    settings: RuntimeSettings,
    *,
    task_ledger: TaskLedger | None = None,
    modal_lifecycle: ModalSandboxLifecycle | None = None,
    task_scheduler: TaskScheduler | None = None,
    task_supervision: TaskSupervisionManager | None = None,
    web_auth: GoogleAuth | None = None,
    web_sessions: LocalSessions | None = None,
    openrouter_vault: SQLiteOpenRouterVault | None = None,
    openrouter_verifier: OpenRouterKeyVerifier | None = None,
    github_connections: SQLiteGitHubConnections | None = None,
    github_client: GitHubClient | None = None,
    repository_authorization: RepositoryAuthorization | None = None,
    checkpoints: CheckpointCoordinator | None = None,
    snapshot_commit=local_commit,
    internal_proxy: bool = False,
) -> FastAPI:
    ledger = task_ledger
    auth_provider = None
    owned_db = ledger is None
    path, snapshot = (
        os.getenv("GG_RUNTIME_DB_PATH"),
        os.getenv("GG_RUNTIME_SNAPSHOT_PATH"),
    )
    if owned_db and (not path or not snapshot):
        raise RuntimeError(
            "GG_RUNTIME_DB_PATH and GG_RUNTIME_SNAPSHOT_PATH are required; "
            "initialize explicitly"
        )

    def wire():
        nonlocal \
            ledger, \
            checkpoints, \
            web_sessions, \
            openrouter_vault, \
            github_connections, \
            repository_authorization, \
            auth_provider
        if ledger is None:
            if not Path(path).exists():
                from gg.runtime.db_cli import restore

                restore(Path(snapshot), Path(path))
            db = SQLiteDB(Path(path))
            ledger = TaskLedger(
                db, CheckpointCoordinator(db, Path(snapshot), snapshot_commit)
            )
        if isinstance(ledger, TaskLedger):
            checkpoints = (
                checkpoints
                or ledger.checkpoints
                or CheckpointCoordinator(
                    ledger.db, ledger.db.path.with_suffix(".snapshot"), local_commit
                )
            )
            if checkpoints.db is not ledger.db:
                raise ValueError("runtime stores must share a database")
            ledger.checkpoints = checkpoints
            web_sessions = web_sessions or LocalSessions(ledger.db, checkpoints)
            for store in (web_sessions, openrouter_vault, github_connections):
                if isinstance(
                    store,
                    (LocalSessions, SQLiteOpenRouterVault, SQLiteGitHubConnections),
                ) and (
                    store.db is not ledger.db or store.checkpoints is not checkpoints
                ):
                    raise ValueError(
                        "runtime stores must share database and coordinator"
                    )
            if openrouter_vault is None and settings.openrouter_vault_key:
                openrouter_vault = SQLiteOpenRouterVault(
                    ledger.db, settings.openrouter_vault_key, checkpoints
                )
            if github_connections is None and settings.github_connection_key:
                github_connections = SQLiteGitHubConnections(
                    ledger.db, checkpoints, settings.github_connection_key
                )
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
        auth_provider = web_auth or GoogleAuth(settings, web_sessions)
        verifier = openrouter_verifier or OpenRouterKeyVerifier()
        lifecycle = modal_lifecycle or lifecycle_from_settings(
            ledger=ledger,
            settings=settings,
            credential_vault=openrouter_vault,
            credential_verifier=verifier,
            repository_authorization=repository_authorization,
        )
        supervision = task_supervision or TaskSupervisionManager(
            ledger=ledger,
            lifecycle=lifecycle,
            settings=settings,
            repository_authorization=repository_authorization,
        )
        limits = StorageLimits.from_settings(settings)
        scheduler = task_scheduler or TaskScheduler(
            ledger=ledger,
            lifecycle=lifecycle,
            capacity=settings.task_capacity,
            lock_path=settings.dispatch_lock_path
            or default_lock_path(deployment=settings.modal_deployment),
            admission_enabled=settings.task_dispatch_enabled,
            poll_seconds=settings.dispatch_poll_seconds,
            supervision=supervision,
            storage_limits=limits,
        )
        app.state.task_ledger = ledger
        app.state.checkpoints = checkpoints
        app.state.task_service = TaskService(
            ledger=ledger,
            settings=settings,
            repository_authorization=repository_authorization,
        )
        app.state.repository_authorization = repository_authorization
        app.state.task_scheduler = scheduler
        app.state.task_supervision = supervision
        app.state.storage_limits = limits
        app.state.web_sessions = web_sessions
        app.include_router(google_auth_router(settings, auth_provider, web_sessions))
        app.include_router(
            openrouter_vault_router(settings, web_sessions, openrouter_vault, verifier)
        )
        app.include_router(
            github_connection_router(
                settings,
                web_sessions,
                github_connections,
                github_client or GitHubClient(settings),
            )
        )
        if settings.web_dist_path:
            app.mount("/", StaticWeb(Path(settings.web_dist_path)))

    @asynccontextmanager
    async def lifespan(app):
        scheduler_started = False
        checkpoint_loop = None
        try:
            if not hasattr(app.state, "task_ledger"):
                wire()
            if checkpoints is not None:
                await durable(checkpoints, checkpoints.db.revision)
            # Reconcile provider identities before admitting requests or runs.
            await app.state.task_scheduler.start()
            scheduler_started = True
            await app.state.task_supervision.startup()
            app.state.recovering = False
            if checkpoints is not None:
                checkpoint_loop = asyncio.create_task(checkpoints.run())
            yield
        finally:
            app.state.recovering = True
            if checkpoint_loop is not None:
                checkpoint_loop.cancel()
                await asyncio.gather(checkpoint_loop, return_exceptions=True)
            if scheduler_started:
                await app.state.task_scheduler.stop()
            if hasattr(app.state, "task_supervision"):
                await app.state.task_supervision.shutdown()
            if auth_provider is not None:
                await auth_provider.close()
            if checkpoints is not None:
                try:
                    await checkpoints.ensure_durable(checkpoints.db.revision)
                finally:
                    if owned_db and ledger is not None:
                        ledger.close()
            elif owned_db and ledger is not None:
                ledger.close()

    app = FastAPI(title="gg-runtime", lifespan=lifespan)
    if settings.web_dist_path:
        if not settings.web_origin:
            raise ValueError("web_origin is required when serving React")
        app.add_middleware(
            OriginGuard, origin=settings.web_origin, internal_proxy=internal_proxy
        )
    app.state.settings = settings
    app.state.recovering = True
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_methods=["GET", "POST", "PUT", "DELETE"],
            allow_headers=["X-API-Key", "Content-Type"],
        )

    @app.exception_handler(sqlite3.Error)
    async def database_error(request: Request, exc: sqlite3.Error):
        return JSONResponse(
            status_code=503,
            content={"detail": "state persistence unavailable"},
            headers={"Retry-After": "1"},
        )

    @app.middleware("http")
    async def persistence_barrier(request: Request, call_next):
        exempt = request.url.path in {"/health", "/ready"}
        # These routes only read local state. Session creation and revocation
        # keep their own barriers; OAuth GET callbacks still use global barriers.
        read_only = request.method in {"GET", "HEAD"} and (
            request.url.path in {"/auth/session", "/tasks"}
            or re.fullmatch(
                r"/tasks/[0-9a-fA-F-]{36}(?:/(?:events|result))?", request.url.path
            )
            is not None
        )
        if not exempt:
            if app.state.recovering:
                return JSONResponse(
                    status_code=503, content={"detail": "runtime recovery in progress"}
                )
            if checkpoints is not None and not read_only:
                try:
                    await durable(checkpoints, checkpoints.db.revision)
                except HTTPException:
                    return JSONResponse(
                        status_code=503,
                        content={"detail": "state persistence unavailable"},
                        headers={"Retry-After": "1"},
                    )
        if request.method == "POST" and (
            request.url.path == "/tasks" or request.url.path.endswith("/retry")
        ):
            dispatch = app.state.task_scheduler.status()
            if not dispatch.reconciled or any(
                item.phase.value == "unresolved_creation"
                for item in dispatch.conditions
            ):
                return JSONResponse(
                    status_code=503,
                    content={"detail": "provider reconciliation incomplete"},
                )
        response = await call_next(request)
        if request.url.path.startswith(("/auth", "/tasks")):
            response.headers["Cache-Control"] = "no-store"
        if (
            not exempt
            and not read_only
            and checkpoints is not None
            and response.status_code < 400
        ):
            try:
                await durable(checkpoints, checkpoints.db.revision)
            except HTTPException:
                return JSONResponse(
                    status_code=503,
                    content={"detail": "state persistence unavailable"},
                    headers={"Retry-After": "1"},
                )
        return response

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/ready", dependencies=[Depends(_check_api_key)])
    def ready(response: Response):
        report = readiness_from_scheduler(
            app.state.task_scheduler,
            database_available=ledger.ping_database(),
            recovering=app.state.recovering,
            persistence_error=checkpoints.last_error if checkpoints else None,
        )
        body = report.model_dump(mode="json")
        body.update(
            version=os.getenv("GG_RUNTIME_VERSION", "local"),
            revision=ledger.db.revision if isinstance(ledger, TaskLedger) else None,
            confirmed_revision=checkpoints.confirmed_revision if checkpoints else None,
        )
        if body["status"] != "ready":
            response.status_code = 503
        return body

    @app.post("/ops/backup", dependencies=[Depends(_check_api_key)])
    async def operational_backup():
        if checkpoints is None or app.state.recovering:
            raise HTTPException(status_code=503, detail="runtime not ready for backup")
        try:
            revision = await checkpoints.checkpoint()
            # No await between checkpoint and open/read: capture the published file
            # before another coroutine can replace it. Return a closed snapshot.
            content = checkpoints.snapshot.read_bytes()
        except Exception:
            raise HTTPException(
                status_code=503, detail="backup persistence failed"
            ) from None
        return Response(
            content,
            media_type="application/vnd.sqlite3",
            headers={"X-Runtime-Revision": str(revision), "Cache-Control": "no-store"},
        )

    app.include_router(task_router, dependencies=[Depends(task_access)])
    app.include_router(event_socket_router)
    if task_ledger is not None:
        wire()
    return app
