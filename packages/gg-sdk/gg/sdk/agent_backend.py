from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, PositiveFloat


if TYPE_CHECKING:
    from gg.sdk.domain import Event, EventKind
    from gg.sdk.local_workspace import LocalWorkspace


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


class PiAgentConfig(BaseModel):
    """Credential-free persisted selection for the Pi RPC backend."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["pi"] = "pi"
    provider: Literal["openrouter"] = "openrouter"
    model: str = Field(default="google/gemini-3.7-flash", min_length=1)
    timeout_seconds: PositiveFloat = 600


AgentConfig = Annotated[PiAgentConfig, Field(discriminator="kind")]


def create_agent_backend(config: AgentConfig) -> AgentBackend:
    """Construct a backend from its safe persisted configuration."""
    from gg.sdk.pi_agent import PiAgentSettings, PiRpcAgent

    return PiRpcAgent(
        PiAgentSettings(
            provider=config.provider,
            model=config.model,
            timeout_seconds=config.timeout_seconds,
        )
    )
