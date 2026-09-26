"""Persisted agent selection shared by the API and sandbox."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, PositiveFloat


DEFAULT_PI_MODEL = "z-ai/glm-5.3-flashx"


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
