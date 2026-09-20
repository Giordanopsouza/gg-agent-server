"""FastAPI control plane for one-container-per-session sandboxes."""

from __future__ import annotations

import secrets
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal, Protocol
from uuid import uuid4

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

from gg.runtime.config import RuntimeSettings
from gg.runtime.github import HttpGitHubGateway
from gg.runtime.ledger import TaskLedger
from gg.runtime.modal_sandbox import ModalSandboxLifecycle, lifecycle_from_settings
from gg.runtime.publication import BotIdentity, DraftPublisher
from gg.runtime.scheduler import TaskScheduler, default_lock_path
from gg.runtime.task_routes import event_socket_router, router as task_router
from gg.runtime.task_service import TaskService
from gg.runtime.task_supervision.manager import TaskSupervisionManager
from gg.sdk.docker_workspace import DockerWorkspace


_CONTROL_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


class Sandbox(Protocol):
    """The lifecycle surface the control plane needs from a sandbox."""

    @property
    def url(self) -> str: ...

    def is_healthy(self) -> bool: ...

    def stop(self) -> None: ...


class SandboxLauncher(Protocol):
    """Provision one sandbox using a newly generated session API key."""

    def start(self, session_api_key: str) -> Sandbox: ...


class DockerSandbox:
    """A running agent-server container owned by the runtime process."""

    # Wrap a started DockerWorkspace so the runtime can treat it like any sandbox.
    def __init__(self, workspace: DockerWorkspace) -> None:
        self._workspace = workspace

    # Where the agent-server inside the container is reachable on the host.
    @property
    def url(self) -> str:
        return self._workspace.host

    # Ping the container's /health endpoint; False if it is down or unreachable.
    def is_healthy(self) -> bool:
        try:
            response = self._workspace.client.get("/health")
            response.raise_for_status()
        except httpx.HTTPError:
            return False
        return True

    # Stop and remove the Docker container for this session.
    def stop(self) -> None:
        self._workspace.stop()


class DockerSandboxLauncher:
    """Start the configured agent-server image with Docker."""

    # Remember which Docker image to run for each new sandbox.
    def __init__(self, *, image: str) -> None:
        self.image = image

    # docker run the agent-server image and pass it a fresh session API key.
    def start(self, session_api_key: str) -> Sandbox:
        workspace = DockerWorkspace(image=self.image, api_key=session_api_key)
        workspace.__enter__()
        return DockerSandbox(workspace)


class StartSessionResponse(BaseModel):
    id: str
    url: str
    session_api_key: str


class SessionResponse(BaseModel):
    id: str
    url: str
    status: Literal["running", "stopped"]


class StopSessionRequest(BaseModel):
    id: str


class _Session:
    # One runtime session: an id, the key for the sandbox, and the live container.
    def __init__(
        self,
        *,
        session_id: str,
        session_api_key: str,
        sandbox: Sandbox,
    ) -> None:
        self.id = session_id
        self.session_api_key = session_api_key
        self.sandbox = sandbox
        self.url = sandbox.url
        self.status: Literal["running", "stopped"] = "running"


class RuntimeService:
    """Own the in-memory mapping from runtime sessions to sandboxes."""

    # Set up the launcher, control-plane key, and empty session registry.
    def __init__(self, launcher: SandboxLauncher, *, control_api_key: str) -> None:
        self._launcher = launcher
        self._control_api_key = control_api_key
        self._sessions: dict[str, _Session] = {}
        self._lock = threading.Lock()

    # Spin up a new container and return its id, url, and sandbox API key.
    def start(self) -> StartSessionResponse:
        session_api_key = self._new_session_api_key()
        sandbox = self._launcher.start(session_api_key)
        session_id = uuid4().hex
        session = _Session(
            session_id=session_id,
            session_api_key=session_api_key,
            sandbox=sandbox,
        )
        with self._lock:
            self._sessions[session_id] = session
        return StartSessionResponse(
            id=session.id,
            url=session.url,
            session_api_key=session.session_api_key,
        )

    # Look up a session; auto-mark it stopped if the container no longer responds.
    def get(self, session_id: str) -> SessionResponse | None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None

        if session.status == "running" and not session.sandbox.is_healthy():
            self._stop(session)
        return SessionResponse(id=session.id, url=session.url, status=session.status)

    # Stop one session by id and return its final status.
    def stop(self, session_id: str) -> SessionResponse | None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
        self._stop(session)
        return SessionResponse(id=session.id, url=session.url, status=session.status)

    # Shut down every session when the runtime process exits.
    def close(self) -> None:
        with self._lock:
            sessions = list(self._sessions.values())
        for session in sessions:
            self._stop(session)

    # Mark a session stopped and tell its sandbox to tear down (idempotent).
    def _stop(self, session: _Session) -> None:
        with self._lock:
            if session.status == "stopped":
                return
            session.status = "stopped"
        session.sandbox.stop()

    # Generate a random key for the sandbox, never the same as the control key.
    def _new_session_api_key(self) -> str:
        key = secrets.token_urlsafe(32)
        while key == self._control_api_key:
            key = secrets.token_urlsafe(32)
        return key


# Reject requests that do not send the runtime control-plane X-API-Key.
def _check_api_key(
    request: Request,
    api_key: str | None = Depends(_CONTROL_API_KEY_HEADER),
) -> None:
    settings: RuntimeSettings = request.app.state.settings
    if not secrets.compare_digest(api_key or "", settings.api_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)


# Pull the shared RuntimeService off the FastAPI app for route handlers.
def _get_service(request: Request) -> RuntimeService:
    return request.app.state.runtime_service


# Wire up the FastAPI app, routes, and cleanup when the process shuts down.
def create_app(
    settings: RuntimeSettings,
    *,
    launcher: SandboxLauncher | None = None,
    task_ledger: TaskLedger | None = None,
    modal_lifecycle: ModalSandboxLifecycle | None = None,
    task_scheduler: TaskScheduler | None = None,
    task_supervision: TaskSupervisionManager | None = None,
) -> FastAPI:
    """Build the standalone runtime app with an injectable Docker boundary."""
    service = RuntimeService(
        launcher or DockerSandboxLauncher(image=settings.image),
        control_api_key=settings.api_key,
    )

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
    )

    # The durable scheduler detaches Modal sandboxes on shutdown. The legacy
    # Docker session service retains its historical stop-everything behavior.
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
            service.close()
            ledger.close()

    app = FastAPI(title="gg-runtime", lifespan=lifespan)
    app.state.settings = settings
    app.state.runtime_service = service
    app.state.task_ledger = ledger
    app.state.task_service = task_service
    app.state.task_scheduler = scheduler
    app.state.task_supervision = supervision
    app.include_router(task_router, dependencies=[Depends(_check_api_key)])
    app.include_router(event_socket_router, dependencies=[Depends(_check_api_key)])

    @app.post(
        "/start",
        response_model=StartSessionResponse,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(_check_api_key)],
    )
    # POST /start — ask for a new sandbox container.
    def start_session(
        service: RuntimeService = Depends(_get_service),
    ) -> StartSessionResponse:
        try:
            return service.start()
        except RuntimeError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc

    @app.get(
        "/sessions/{session_id}",
        response_model=SessionResponse,
        dependencies=[Depends(_check_api_key)],
    )
    # GET /sessions/{id} — check whether a session is still running.
    def get_session(
        session_id: str,
        service: RuntimeService = Depends(_get_service),
    ) -> SessionResponse:
        session = service.get(session_id)
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return session

    @app.post(
        "/stop",
        response_model=SessionResponse,
        dependencies=[Depends(_check_api_key)],
    )
    # POST /stop — kill a session's container by id.
    def stop_session(
        body: StopSessionRequest,
        service: RuntimeService = Depends(_get_service),
    ) -> SessionResponse:
        session = service.stop(body.id)
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return session

    return app
