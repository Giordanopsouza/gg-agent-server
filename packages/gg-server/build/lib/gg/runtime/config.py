"""Environment-backed configuration for the standalone runtime process."""
from __future__ import annotations

import os

from pydantic import BaseModel, ConfigDict, Field, field_validator


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8001
DEFAULT_IMAGE = "gg-agent-server:dev"
DEFAULT_TASK_DB_PATH = "gg-tasks.sqlite"
DEFAULT_MAX_PROMPT_CHARS = 16_000
DEFAULT_MAX_BASE_REF_CHARS = 200
DEFAULT_MAX_IDEMPOTENCY_KEY_CHARS = 256
SUPPORTED_TASK_SCHEMA_VERSION = 1


class RuntimeSettings(BaseModel):
    """Frozen settings for the control plane and its sandbox image."""

    model_config = ConfigDict(frozen=True)

    api_key: str
    host: str = DEFAULT_HOST
    port: int = Field(default=DEFAULT_PORT, ge=1, le=65535)
    image: str = DEFAULT_IMAGE
    task_db_path: str = DEFAULT_TASK_DB_PATH
    repository_allowlist: tuple[str, ...] = Field(default_factory=tuple)
    max_prompt_chars: int = Field(default=DEFAULT_MAX_PROMPT_CHARS, ge=1)
    max_base_ref_chars: int = Field(default=DEFAULT_MAX_BASE_REF_CHARS, ge=1)
    max_idempotency_key_chars: int = Field(
        default=DEFAULT_MAX_IDEMPOTENCY_KEY_CHARS, ge=1
    )

    @field_validator("api_key")
    @classmethod
    # The control-plane key must be present and not have stray spaces.
    def validate_api_key(cls, value: str) -> str:
        if not value or value != value.strip():
            raise ValueError(
                "api_key must be non-empty and cannot contain surrounding whitespace"
            )
        return value

    @field_validator("image")
    @classmethod
    # The Docker image name cannot be blank.
    def validate_image(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("image must not be empty")
        return value

    @field_validator("task_db_path")
    @classmethod
    # The SQLite path must be usable; ":memory:" is allowed for tests.
    def validate_task_db_path(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("task_db_path must not be empty")
        return value

    @field_validator("repository_allowlist")
    @classmethod
    # Allowlist entries are stripped and de-duplicated so lookups are exact.
    def normalize_allowlist(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized: list[str] = []
        for entry in value:
            stripped = entry.strip()
            if stripped and stripped not in normalized:
                normalized.append(stripped)
        return tuple(normalized)


# Turn GG_RUNTIME_PORT into an int, or use 8001 if unset.
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


# Turn a comma-separated env var into a tuple of repository names.
def _parse_allowlist(raw: str | None) -> tuple[str, ...]:
    if raw is None or not raw.strip():
        return ()
    return tuple(
        entry.strip()
        for entry in raw.split(",")
        if entry.strip()
    )


def _parse_int(raw: str | None, default: int) -> int:
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"expected an integer, got {raw!r}") from exc


# Read all runtime settings from environment variables at startup.
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
        task_db_path=os.getenv("GG_TASK_DB_PATH", DEFAULT_TASK_DB_PATH),
        repository_allowlist=_parse_allowlist(os.getenv("GG_REPOSITORY_ALLOWLIST")),
        max_prompt_chars=_parse_int(
            os.getenv("GG_MAX_PROMPT_CHARS"), DEFAULT_MAX_PROMPT_CHARS
        ),
        max_base_ref_chars=_parse_int(
            os.getenv("GG_MAX_BASE_REF_CHARS"), DEFAULT_MAX_BASE_REF_CHARS
        ),
        max_idempotency_key_chars=_parse_int(
            os.getenv("GG_MAX_IDEMPOTENCY_KEY_CHARS"),
            DEFAULT_MAX_IDEMPOTENCY_KEY_CHARS,
        ),
    )

