from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Annotated, Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, PositiveFloat


if TYPE_CHECKING:
    from gg.sdk.domain import Event, EventKind
    from gg.sdk.local_workspace import LocalWorkspace


DEFAULT_PI_MODEL = "z-ai/glm-5.3-flashx"


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


class PiAgentConfig(BaseModel):
    """Credential-free persisted selection for the Pi RPC backend."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["pi"] = "pi"
    provider: Literal["openrouter"] = "openrouter"
    model: str = Field(default=DEFAULT_PI_MODEL, min_length=1)
    timeout_seconds: PositiveFloat = 600
    command_ack_timeout_seconds: PositiveFloat = 5
    cancel_grace_seconds: PositiveFloat = 5


AgentConfig = Annotated[PiAgentConfig, Field(discriminator="kind")]


def create_agent_backend(config: AgentConfig) -> AgentBackend:
    """Construct a backend from its safe persisted configuration."""
    from gg.sdk.pi_agent import PiAgentSettings, PiRpcAgent

    return PiRpcAgent(
        PiAgentSettings(
            provider=config.provider,
            model=config.model,
            timeout_seconds=config.timeout_seconds,
            command_ack_timeout_seconds=config.command_ack_timeout_seconds,
            cancel_grace_seconds=config.cancel_grace_seconds,
        )
    )
