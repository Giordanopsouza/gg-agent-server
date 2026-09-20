"""Concrete Modal sandbox lifecycle for durable background tasks.

This is deliberately one provider integration, not a provider registry.  The
legacy Docker runtime remains a separate demo surface in ``gg.runtime.app``.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import secrets
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx
import modal

from gg.runtime.config import RuntimeSettings
from gg.runtime.ledger import (
    SandboxCreationRecord,
    SandboxProviderState,
    TaskLedger,
)


AGENT_SERVER_PORT = 8000
DEFAULT_CPU = (2.0, 2.0)
DEFAULT_MEMORY = (4096, 4096)
DEFAULT_STARTUP_TIMEOUT_SECONDS = 5 * 60
DEFAULT_PROVIDER_TIMEOUT_SECONDS = 70 * 60
IDENTITY_TAG = "gg_identity"
DEPLOYMENT_TAG = "gg_deployment"
TASK_TAG = "gg_task_id"


class ModalLifecycleError(RuntimeError):
    """Base error for lifecycle operations."""


class AmbiguousProviderStateError(ModalLifecycleError):
    """The provider did not establish whether a sandbox exists or stopped."""


class SandboxNotFoundError(ModalLifecycleError):
    """No durable creation intent exists for the requested task."""


class ConflictingSandboxesError(ModalLifecycleError):
    """More than one provider sandbox has the same deterministic identity."""


class _ProviderNotFoundError(Exception):
    pass


class ProviderHandle(Protocol):
    @property
    def object_id(self) -> str: ...


class Provider(Protocol):
    async def create(
        self,
        *,
        name: str,
        tags: dict[str, str],
        session_api_key: str,
        sandbox_env: dict[str, str],
        cpu: tuple[float, float],
        memory: tuple[int, int],
        startup_timeout: int,
        provider_timeout: int,
    ) -> ProviderHandle: ...

    async def from_id(self, provider_id: str) -> ProviderHandle: ...

    async def find(self, *, tags: dict[str, str]) -> list[ProviderHandle]: ...

    async def poll(self, handle: ProviderHandle) -> int | None: ...

    async def wait_until_ready(
        self, handle: ProviderHandle, *, timeout: int
    ) -> None: ...

    async def connect_token(
        self, handle: ProviderHandle, *, port: int
    ) -> tuple[str, str]: ...

    async def terminate(self, handle: ProviderHandle) -> None: ...

    async def detach(self, handle: ProviderHandle) -> None: ...


class ModalProvider:
    """Thin asynchronous adapter around the pinned Modal Python SDK."""

    def __init__(
        self,
        *,
        app_name: str,
        image_name: str,
        environment_name: str | None = None,
    ) -> None:
        self._app_name = app_name
        self._image_name = image_name
        self._environment_name = environment_name
        self._app: Any | None = None

    def _load_app(self) -> Any:
        if self._app is None:
            self._app = modal.App.lookup(
                self._app_name,
                create_if_missing=False,
                environment_name=self._environment_name,
            )
        return self._app

    def _create_sync(self, **kwargs: Any) -> ProviderHandle:
        app = self._load_app()
        image = modal.Image.from_name(
            self._image_name, environment_name=self._environment_name
        )
        return modal.Sandbox.create(
            "python",
            "-m",
            "gg.server",
            "--host",
            "0.0.0.0",
            "--port",
            str(AGENT_SERVER_PORT),
            app=app,
            image=image,
            name=kwargs["name"],
            tags=kwargs["tags"],
            env=kwargs["sandbox_env"],
            cpu=kwargs["cpu"],
            memory=kwargs["memory"],
            timeout=kwargs["provider_timeout"],
            readiness_probe=modal.Probe.with_tcp(AGENT_SERVER_PORT),
            environment_name=self._environment_name,
        )

    async def create(self, **kwargs: Any) -> ProviderHandle:
        return await asyncio.to_thread(self._create_sync, **kwargs)

    async def from_id(self, provider_id: str) -> ProviderHandle:
        try:
            return await asyncio.to_thread(modal.Sandbox.from_id, provider_id)
        except modal.exception.NotFoundError as exc:
            raise _ProviderNotFoundError(provider_id) from exc

    def _find_sync(self, tags: dict[str, str]) -> list[ProviderHandle]:
        app = self._load_app()
        return list(modal.Sandbox.list(app_id=app.app_id, tags=tags))

    async def find(self, *, tags: dict[str, str]) -> list[ProviderHandle]:
        return await asyncio.to_thread(self._find_sync, tags)

    async def poll(self, handle: ProviderHandle) -> int | None:
        return await asyncio.to_thread(handle.poll)  # type: ignore[attr-defined]

    async def wait_until_ready(self, handle: ProviderHandle, *, timeout: int) -> None:
        await asyncio.to_thread(  # type: ignore[attr-defined]
            handle.wait_until_ready, timeout=timeout
        )

    async def connect_token(
        self, handle: ProviderHandle, *, port: int
    ) -> tuple[str, str]:
        credentials = await asyncio.to_thread(  # type: ignore[attr-defined]
            handle.create_connect_token, port=port
        )
        return credentials.url, credentials.token

    async def terminate(self, handle: ProviderHandle) -> None:
        await asyncio.to_thread(handle.terminate, wait=True)  # type: ignore[attr-defined]

    async def detach(self, handle: ProviderHandle) -> None:
        await asyncio.to_thread(handle.detach)  # type: ignore[attr-defined]


@dataclass(frozen=True)
class SandboxSnapshot:
    """Credential-free lifecycle result safe for task/control-plane output."""

    task_id: str
    provider_id: str | None
    state: SandboxProviderState
    detail: str | None = None


@dataclass(frozen=True)
class SandboxConnection:
    """Private authenticated HTTPS/WebSocket connection material."""

    base_url: str
    _connect_token: str = field(repr=False)
    _session_api_key: str = field(repr=False)

    def __post_init__(self) -> None:
        if not self.base_url.startswith("https://"):
            raise ModalLifecycleError("Modal connect URL must use encrypted HTTPS")

    def http_client(self, **kwargs: Any) -> httpx.AsyncClient:
        headers = dict(kwargs.pop("headers", {}))
        headers.update(self._headers())
        return httpx.AsyncClient(base_url=self.base_url, headers=headers, **kwargs)

    def websocket_target(self, path: str) -> tuple[str, dict[str, str]]:
        """Return a WSS URL and auth headers for an internal WS client."""

        normalized = "/" + path.lstrip("/")
        url = self.base_url.rstrip("/").replace("https://", "wss://", 1)
        return url + normalized, self._headers()

    def websocket_auth_frame(self) -> dict[str, str]:
        """Return the agent-server authentication frame sent after WS connect."""

        return {"type": "auth", "session_api_key": self._session_api_key}

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._connect_token}",
            "X-API-Key": self._session_api_key,
        }


def _sandbox_identity(deployment: str, task_id: str) -> tuple[str, dict[str, str]]:
    identity = f"{deployment}:{task_id}"
    deployment_slug = re.sub(r"[^a-zA-Z0-9_.-]", "-", deployment).strip("-._")
    deployment_slug = deployment_slug[:20] or "deployment"
    digest = hashlib.sha256(identity.encode()).hexdigest()[:20]
    name = f"gg-{deployment_slug}-{digest}"
    tags = {
        IDENTITY_TAG: identity,
        DEPLOYMENT_TAG: deployment,
        TASK_TAG: task_id,
    }
    return name, tags


class ModalSandboxLifecycle:
    """Durable create/reconnect/connect/detach/terminate operations."""

    def __init__(
        self,
        *,
        ledger: TaskLedger,
        provider: Provider,
        deployment: str,
        cpu: tuple[float, float] = DEFAULT_CPU,
        memory: tuple[int, int] = DEFAULT_MEMORY,
        startup_timeout: int = DEFAULT_STARTUP_TIMEOUT_SECONDS,
        provider_timeout: int = DEFAULT_PROVIDER_TIMEOUT_SECONDS,
        sandbox_env: dict[str, str] | None = None,
    ) -> None:
        self._ledger = ledger
        self._provider = provider
        self._deployment = deployment
        self._sandbox_env = sandbox_env or {}
        self._cpu = cpu
        self._memory = memory
        self._startup_timeout = startup_timeout
        self._provider_timeout = provider_timeout

    async def create(self, task_id: str) -> SandboxSnapshot:
        name, tags = _sandbox_identity(self._deployment, task_id)
        record, created = self._ledger.begin_sandbox_creation(
            task_id=task_id,
            deployment=self._deployment,
            sandbox_name=name,
            tags_json=json.dumps(tags, sort_keys=True, separators=(",", ":")),
            session_api_key=secrets.token_urlsafe(32),
        )
        if not created:
            snapshot, handle = await self._reconnect(record)
            if snapshot.state is SandboxProviderState.RUNNING:
                return snapshot
            if snapshot.state is not SandboxProviderState.STOPPED:
                raise AmbiguousProviderStateError(
                    f"sandbox creation for task {task_id} is unresolved"
                )
            if record.provider_id is not None:
                return snapshot
            # A successful identity lookup confirmed that the pre-network-call
            # intent has no provider resource, so retrying creation is safe.

        try:
            env = dict(self._sandbox_env)
            env["GG_SESSION_API_KEYS"] = record.session_api_key
            handle = await self._provider.create(
                name=record.sandbox_name,
                tags=json.loads(record.tags_json),
                session_api_key=record.session_api_key,
                sandbox_env=env,
                cpu=self._cpu,
                memory=self._memory,
                startup_timeout=self._startup_timeout,
                provider_timeout=self._provider_timeout,
            )
        except Exception as exc:
            self._ledger.update_sandbox_creation(
                task_id,
                provider_state=SandboxProviderState.UNKNOWN,
                detail=f"create response unresolved: {type(exc).__name__}",
            )
            raise AmbiguousProviderStateError(
                f"Modal create response for task {task_id} was unresolved"
            ) from exc

        # This write is deliberately the first operation after create returns.
        record = self._ledger.update_sandbox_creation(
            task_id,
            provider_id=handle.object_id,
            provider_state=SandboxProviderState.CREATING,
        )
        try:
            await self._provider.wait_until_ready(handle, timeout=self._startup_timeout)
        except Exception as exc:
            self._ledger.update_sandbox_creation(
                task_id,
                provider_state=SandboxProviderState.UNKNOWN,
                detail=f"startup readiness unresolved: {type(exc).__name__}",
            )
            raise AmbiguousProviderStateError(
                f"Modal startup for task {task_id} was unresolved"
            ) from exc
        self._ledger.update_sandbox_creation(
            task_id, provider_state=SandboxProviderState.RUNNING
        )
        return SandboxSnapshot(
            task_id, record.provider_id, SandboxProviderState.RUNNING
        )

    async def inspect(self, task_id: str) -> SandboxSnapshot:
        record = self._record(task_id)
        snapshot, _ = await self._reconnect(record)
        return snapshot

    async def reconnect(self, task_id: str) -> SandboxSnapshot:
        return await self.inspect(task_id)

    async def connect(self, task_id: str) -> SandboxConnection:
        record = self._record(task_id)
        snapshot, handle = await self._reconnect(record)
        if snapshot.state is not SandboxProviderState.RUNNING or handle is None:
            raise ModalLifecycleError(
                f"sandbox for task {task_id} is not confirmed running"
            )
        try:
            url, token = await self._provider.connect_token(
                handle, port=AGENT_SERVER_PORT
            )
        except Exception as exc:
            # Connectivity failure does not establish provider termination.
            self._ledger.update_sandbox_creation(
                task_id,
                provider_state=SandboxProviderState.UNKNOWN,
                detail=f"connect request failed: {type(exc).__name__}",
            )
            raise AmbiguousProviderStateError(
                f"sandbox connection for task {task_id} is unreachable"
            ) from exc
        return SandboxConnection(url, token, record.session_api_key)

    async def health(self, task_id: str) -> SandboxSnapshot:
        """Check agent-server health without treating failure as termination."""

        try:
            connection = await self.connect(task_id)
            async with connection.http_client(timeout=10) as client:
                response = await client.get("/health")
                response.raise_for_status()
        except (httpx.HTTPError, AmbiguousProviderStateError) as exc:
            updated = self._ledger.update_sandbox_creation(
                task_id,
                provider_state=SandboxProviderState.UNKNOWN,
                detail=f"health request failed: {type(exc).__name__}",
            )
            return self._snapshot(updated)
        updated = self._ledger.update_sandbox_creation(
            task_id, provider_state=SandboxProviderState.RUNNING
        )
        return self._snapshot(updated)

    async def detach(self, task_id: str) -> SandboxSnapshot:
        record = self._record(task_id)
        snapshot, handle = await self._reconnect(record)
        if handle is not None:
            try:
                await self._provider.detach(handle)
            except Exception as exc:
                self._ledger.update_sandbox_creation(
                    task_id,
                    provider_state=SandboxProviderState.UNKNOWN,
                    detail=f"detach failed: {type(exc).__name__}",
                )
                raise AmbiguousProviderStateError(
                    f"sandbox detach for task {task_id} was unresolved"
                ) from exc
        return snapshot

    async def terminate(self, task_id: str) -> SandboxSnapshot:
        record = self._record(task_id)
        snapshot, handle = await self._reconnect(record)
        if snapshot.state is SandboxProviderState.STOPPED:
            return snapshot
        if handle is None:
            raise AmbiguousProviderStateError(
                f"sandbox termination for task {task_id} cannot be confirmed"
            )
        try:
            await self._provider.terminate(handle)
            return await self.inspect(task_id)
        except Exception as exc:
            self._ledger.update_sandbox_creation(
                task_id,
                provider_state=SandboxProviderState.UNKNOWN,
                detail=f"termination response unresolved: {type(exc).__name__}",
            )
            raise AmbiguousProviderStateError(
                f"Modal termination for task {task_id} was unresolved"
            ) from exc

    def _record(self, task_id: str) -> SandboxCreationRecord:
        record = self._ledger.get_sandbox_creation(task_id)
        if record is None:
            raise SandboxNotFoundError(f"no sandbox creation intent for task {task_id}")
        return record

    async def _reconnect(
        self, record: SandboxCreationRecord
    ) -> tuple[SandboxSnapshot, ProviderHandle | None]:
        handle: ProviderHandle | None = None
        if record.provider_id is not None:
            try:
                handle = await self._provider.from_id(record.provider_id)
            except _ProviderNotFoundError:
                updated = self._ledger.update_sandbox_creation(
                    record.task_id,
                    provider_state=SandboxProviderState.STOPPED,
                    detail="provider confirmed sandbox absent",
                )
                return self._snapshot(updated), None
            except Exception as exc:
                updated = self._ledger.update_sandbox_creation(
                    record.task_id,
                    provider_state=SandboxProviderState.UNKNOWN,
                    detail=f"provider lookup failed: {type(exc).__name__}",
                )
                return self._snapshot(updated), None
        else:
            try:
                matches = await self._provider.find(tags=json.loads(record.tags_json))
            except Exception as exc:
                updated = self._ledger.update_sandbox_creation(
                    record.task_id,
                    provider_state=SandboxProviderState.UNKNOWN,
                    detail=f"identity discovery failed: {type(exc).__name__}",
                )
                return self._snapshot(updated), None
            if len(matches) > 1:
                updated = self._ledger.update_sandbox_creation(
                    record.task_id,
                    provider_state=SandboxProviderState.UNKNOWN,
                    detail="multiple provider sandboxes match deterministic identity",
                )
                raise ConflictingSandboxesError(
                    updated.detail or "conflicting sandboxes"
                )
            if not matches:
                updated = self._ledger.update_sandbox_creation(
                    record.task_id,
                    provider_state=SandboxProviderState.STOPPED,
                    detail="provider confirmed deterministic identity absent",
                )
                return self._snapshot(updated), None
            handle = matches[0]
            record = self._ledger.update_sandbox_creation(
                record.task_id,
                provider_id=handle.object_id,
                provider_state=SandboxProviderState.CREATING,
            )

        try:
            return_code = await self._provider.poll(handle)
        except Exception as exc:
            updated = self._ledger.update_sandbox_creation(
                record.task_id,
                provider_state=SandboxProviderState.UNKNOWN,
                detail=f"provider status failed: {type(exc).__name__}",
            )
            return self._snapshot(updated), handle
        state = (
            SandboxProviderState.RUNNING
            if return_code is None
            else SandboxProviderState.STOPPED
        )
        updated = self._ledger.update_sandbox_creation(
            record.task_id,
            provider_state=state,
            detail=None if return_code is None else f"provider exit code {return_code}",
        )
        return self._snapshot(updated), handle

    @staticmethod
    def _snapshot(record: SandboxCreationRecord) -> SandboxSnapshot:
        return SandboxSnapshot(
            task_id=record.task_id,
            provider_id=record.provider_id,
            state=record.provider_state,
            detail=record.detail,
        )


def sandbox_env_from_settings(settings: RuntimeSettings) -> dict[str, str]:
    """Build non-session environment variables forwarded into each sandbox."""

    env: dict[str, str] = {}
    if settings.github_clone_token:
        env["GG_GITHUB_CLONE_TOKEN"] = settings.github_clone_token
    if settings.openrouter_api_key:
        env["OPENROUTER_API_KEY"] = settings.openrouter_api_key
    if settings.repository_profiles:
        env["GG_REPOSITORY_PROFILES_JSON"] = json.dumps(
            [profile.model_dump() for profile in settings.repository_profiles]
        )
    return env


def lifecycle_from_settings(
    *,
    ledger: TaskLedger,
    settings: RuntimeSettings,
    provider: Provider | None = None,
) -> ModalSandboxLifecycle:
    """Construct the single concrete production lifecycle from runtime settings."""

    modal_provider = provider or ModalProvider(
        app_name=settings.modal_app_name,
        image_name=settings.modal_image_name,
    )
    return ModalSandboxLifecycle(
        ledger=ledger,
        provider=modal_provider,
        deployment=settings.modal_deployment,
        cpu=(settings.modal_cpu_request, settings.modal_cpu_limit),
        memory=(
            settings.modal_memory_request_mib,
            settings.modal_memory_limit_mib,
        ),
        startup_timeout=settings.modal_startup_timeout_seconds,
        provider_timeout=settings.modal_provider_timeout_seconds,
        sandbox_env=sandbox_env_from_settings(settings),
    )


__all__ = [
    "AGENT_SERVER_PORT",
    "AmbiguousProviderStateError",
    "ConflictingSandboxesError",
    "DEFAULT_CPU",
    "DEFAULT_MEMORY",
    "DEFAULT_PROVIDER_TIMEOUT_SECONDS",
    "DEFAULT_STARTUP_TIMEOUT_SECONDS",
    "ModalLifecycleError",
    "ModalProvider",
    "ModalSandboxLifecycle",
    "SandboxConnection",
    "SandboxNotFoundError",
    "SandboxSnapshot",
    "lifecycle_from_settings",
    "sandbox_env_from_settings",
]
