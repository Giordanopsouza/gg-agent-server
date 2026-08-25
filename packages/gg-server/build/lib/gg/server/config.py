"""Server settings loaded from the environment.

- # Only this module in gg.server may read os.environ. Everything else
  calls get_settings() and trusts the frozen Settings it gets back.

Parsing happens once at the boundary; the rest of the server never
touches env vars. That keeps configuration a single source of truth
and makes the invalid-port error message name the offending variable.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DEFAULT_CONVERSATIONS_DIR = Path("workspace/conversations")
DEFAULT_WORKSPACE_DIR = Path("workspace/project")


class Settings(BaseModel):
    """Frozen server configuration parsed from GG_* env vars."""

    # - # frozen=True: once parsed, settings cannot be mutated by anyone.
    model_config = ConfigDict(frozen=True)

    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    conversations_dir: Path = DEFAULT_CONVERSATIONS_DIR
    workspace_dir: Path = DEFAULT_WORKSPACE_DIR
    # - # Empty list means an open server (no auth). See task 010 for enforcement.
    session_api_keys: list[str] = Field(default_factory=list)


def _parse_port(raw: str | None) -> int:
    """Parse GG_PORT or fall back to the default.

    - # Raises ValueError naming GG_PORT so the operator knows which var to fix.
    """
    if raw is None or raw == "":
        return DEFAULT_PORT
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"GG_PORT must be an integer, got {raw!r}") from exc
    if not (1 <= value <= 65535):
        raise ValueError(f"GG_PORT must be between 1 and 65535, got {value}")
    return value


def _parse_session_api_keys(raw: str | None) -> list[str]:
    """Parse GG_SESSION_API_KEYS as a comma-separated list.

    - # Empty or missing means an open server. Whitespace around keys is trimmed.
    """
    if raw is None or raw.strip() == "":
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def _load_settings() -> Settings:
    """Read GG_* env vars and build a frozen Settings.

    - # This is the only place that calls os.getenv. The boundary test enforces that.
    """
    data: dict[str, Any] = {}

    if (host := os.getenv("GG_HOST")) :
        data["host"] = host

    data["port"] = _parse_port(os.getenv("GG_PORT"))

    if (conversations_dir := os.getenv("GG_CONVERSATIONS_DIR")) :
        data["conversations_dir"] = Path(conversations_dir)

    if (workspace_dir := os.getenv("GG_WORKSPACE_DIR")) :
        data["workspace_dir"] = Path(workspace_dir)

    data["session_api_keys"] = _parse_session_api_keys(os.getenv("GG_SESSION_API_KEYS"))

    try:
        return Settings.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"Invalid server settings: {exc}") from exc


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return the process-wide singleton Settings.

    - # The only public accessor. Reads env on first call, then caches.
    """
    global _settings
    if _settings is None:
        _settings = _load_settings()
    return _settings


def reset_settings() -> None:
    """Clear the cached singleton. Test-only: lets a test re-read env."""
    global _settings
    _settings = None
