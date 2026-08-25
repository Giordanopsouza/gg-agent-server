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

    def __init__(self, workspace: DockerWorkspace) -> None:
        self._workspace = workspace

    @property
    def url(self) -> str:
        return self._workspace.host

    def is_healthy(self) -> bool:
        try:
            response = self._workspace.client.get("/health")
            response.raise_for_status()
        except httpx.HTTPError:
            return False
        return True

    def stop(self) -> None:
        self._workspace.stop()


class DockerSandboxLauncher:
    """Start the configured agent-server image with Docker."""

    def __init__(self, *, image: str) -> None:
        self.image = image

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

    def __init__(self, launcher: SandboxLauncher, *, control_api_key: str) -> None:
        self._launcher = launcher
        self._control_api_key = control_api_key
        self._sessions: dict[str, _Session] = {}
        self._lock = threading.Lock()

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

    def get(self, session_id: str) -> SessionResponse | None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None

        if session.status == "running" and not session.sandbox.is_healthy():
            self._stop(session)
        return SessionResponse(id=session.id, url=session.url, status=session.status)

    def stop(self, session_id: str) -> SessionResponse | None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
        self._stop(session)
        return SessionResponse(id=session.id, url=session.url, status=session.status)

    def close(self) -> None:
        with self._lock:
            sessions = list(self._sessions.values())
        for session in sessions:
            self._stop(session)

    def _stop(self, session: _Session) -> None:
        with self._lock:
            if session.status == "stopped":
                return
            session.status = "stopped"
        session.sandbox.stop()

    def _new_session_api_key(self) -> str:
        key = secrets.token_urlsafe(32)
        while key == self._control_api_key:
            key = secrets.token_urlsafe(32)
        return key


def _check_api_key(
    request: Request,
    api_key: str | None = Depends(_CONTROL_API_KEY_HEADER),
) -> None:
    settings: RuntimeSettings = request.app.state.settings
    if not secrets.compare_digest(api_key or "", settings.api_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)


def _get_service(request: Request) -> RuntimeService:
    return request.app.state.runtime_service


def create_app(
    settings: RuntimeSettings,
    *,
    launcher: SandboxLauncher | None = None,
) -> FastAPI:
    """Build the standalone runtime app with an injectable Docker boundary."""
    service = RuntimeService(
        launcher or DockerSandboxLauncher(image=settings.image),
        control_api_key=settings.api_key,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            service.close()

    app = FastAPI(title="gg-runtime", lifespan=lifespan)
    app.state.settings = settings
    app.state.runtime_service = service

    @app.post(
        "/start",
        response_model=StartSessionResponse,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(_check_api_key)],
    )
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
    def stop_session(
        body: StopSessionRequest,
        service: RuntimeService = Depends(_get_service),
    ) -> SessionResponse:
        session = service.stop(body.id)
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return session

    return app
