from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, PositiveFloat


if TYPE_CHECKING:
    from gg.sdk.domain import Event, EventKind
    from gg.sdk.local_workspace import LocalWorkspace
    from gg.sdk.tools import ToolRegistry


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


class DummyAgentConfig(BaseModel):
    """Persisted selection for the deterministic offline backend."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["dummy"] = "dummy"


class PiAgentConfig(BaseModel):
    """Credential-free persisted selection for the Pi RPC backend."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["pi"] = "pi"
    provider: Literal["openrouter"] = "openrouter"
    model: str = Field(default="google/gemini-3.7-flash", min_length=1)
    timeout_seconds: PositiveFloat = 600


AgentConfig = Annotated[DummyAgentConfig | PiAgentConfig, Field(discriminator="kind")]


def create_agent_backend(
    config: AgentConfig,
    *,
    tool_registry: ToolRegistry | None = None,
) -> AgentBackend:
    """Construct a backend from its safe persisted configuration."""
    if isinstance(config, PiAgentConfig):
        from gg.sdk.pi_agent import PiAgentSettings, PiRpcAgent

        return PiRpcAgent(
            PiAgentSettings(
                provider=config.provider,
                model=config.model,
                timeout_seconds=config.timeout_seconds,
            )
        )

    from gg.sdk.dummy_agent import DummyAgentBackend

    return DummyAgentBackend(tool_registry)
