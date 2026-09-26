"""Sandbox-local agent backend protocol and construction."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from gg.sdk.agent_backend import AgentConfig
from gg.sdk.domain import Event, EventKind


if TYPE_CHECKING:
    from gg.server.agent.local_workspace import LocalWorkspace


class EventEmitter(Protocol):
    def __call__(self, kind: EventKind, payload: dict[str, Any]) -> Event: ...


class AgentBackend(Protocol):
    """Run one agent turn against a local workspace."""

    def run(
        self,
        prompt: str,
        workspace: LocalWorkspace,
        emit: EventEmitter,
    ) -> None: ...


@runtime_checkable
class RunningAgentBackend(Protocol):
    """Optional control surface implemented by a live agent backend."""

    def set_settling_listener(self, listener: Callable[[], None] | None) -> None: ...

    def steer(self, message: str) -> tuple[bool, str | None]: ...

    def cancel(self) -> None: ...


def create_agent_backend(config: AgentConfig) -> AgentBackend:
    """Construct an agent from its safe persisted configuration."""
    from gg.server.agent.pi_agent import PiAgentSettings, PiRpcAgent

    return PiRpcAgent(
        PiAgentSettings(
            provider=config.provider,
            model=config.model,
            timeout_seconds=config.timeout_seconds,
            command_ack_timeout_seconds=config.command_ack_timeout_seconds,
            cancel_grace_seconds=config.cancel_grace_seconds,
        )
    )
