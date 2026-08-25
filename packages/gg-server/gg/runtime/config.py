"""Environment-backed configuration for the standalone runtime process."""
from __future__ import annotations

import os

from pydantic import BaseModel, ConfigDict, Field, field_validator


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8001
DEFAULT_IMAGE = "gg-agent-server:dev"


class RuntimeSettings(BaseModel):
    """Frozen settings for the control plane and its sandbox image."""

    model_config = ConfigDict(frozen=True)

    api_key: str
    host: str = DEFAULT_HOST
    port: int = Field(default=DEFAULT_PORT, ge=1, le=65535)
    image: str = DEFAULT_IMAGE

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, value: str) -> str:
        if not value or value != value.strip():
            raise ValueError(
                "api_key must be non-empty and cannot contain surrounding whitespace"
            )
        return value

    @field_validator("image")
    @classmethod
    def validate_image(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("image must not be empty")
        return value


def _parse_port(raw: str | None) -> int:
    if raw is None or raw == "":
        return DEFAULT_PORT
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"GG_RUNTIME_PORT must be an integer, got {raw!r}") from exc
    if not (1 <= value <= 65535):
        raise ValueError(f"GG_RUNTIME_PORT must be between 1 and 65535, got {value}")
    return value


def load_settings() -> RuntimeSettings:
    """Read runtime configuration once at the process boundary."""
    api_key = os.getenv("GG_RUNTIME_API_KEY")
    if api_key is None or not api_key.strip():
        raise ValueError("GG_RUNTIME_API_KEY must be set to a non-empty value")
    if api_key != api_key.strip():
        raise ValueError("GG_RUNTIME_API_KEY cannot contain surrounding whitespace")

    image = os.getenv("GG_RUNTIME_IMAGE", DEFAULT_IMAGE)
    if not image.strip():
        raise ValueError("GG_RUNTIME_IMAGE must not be empty")

    return RuntimeSettings(
        api_key=api_key,
        host=os.getenv("GG_RUNTIME_HOST", DEFAULT_HOST),
        port=_parse_port(os.getenv("GG_RUNTIME_PORT")),
        image=image,
    )
