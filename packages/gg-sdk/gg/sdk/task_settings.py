"""Environment-backed settings for the background-task HTTP client."""

from __future__ import annotations

import os
from ipaddress import ip_address
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, field_validator


DEFAULT_RUNTIME_HOST = "127.0.0.1"
DEFAULT_RUNTIME_PORT = 8001


class TaskClientSettings(BaseModel):
    """Credential-bearing connection details for the runtime task API."""

    model_config = ConfigDict(frozen=True)

    api_url: str
    api_key: str
    timeout: float = 30.0

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, value: str) -> str:
        if not value or value != value.strip():
            raise ValueError(
                "api_key must be non-empty and cannot contain surrounding whitespace"
            )
        return value

    @field_validator("api_url")
    @classmethod
    def validate_api_url(cls, value: str) -> str:
        normalized = value.rstrip("/")
        parsed = urlsplit(normalized)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("api_url must use http or https")
        if not parsed.netloc:
            raise ValueError("api_url must include a host")
        if parsed.scheme == "http" and not _is_loopback_host(parsed.hostname):
            raise ValueError(
                "insecure http is only allowed for loopback development hosts"
            )
        return normalized


def load_task_client_settings() -> TaskClientSettings:
    """Read task client configuration from the process environment."""
    api_key = os.getenv("GG_RUNTIME_API_KEY")
    if api_key is None or not api_key.strip():
        raise ValueError("GG_RUNTIME_API_KEY must be set to a non-empty value")

    explicit = os.getenv("GG_TASK_API_URL")
    if explicit is not None and explicit.strip():
        api_url = explicit.strip().rstrip("/")
    else:
        host = os.getenv("GG_RUNTIME_HOST", DEFAULT_RUNTIME_HOST)
        port_raw = os.getenv("GG_RUNTIME_PORT")
        port = int(port_raw) if port_raw is not None else DEFAULT_RUNTIME_PORT
        scheme = "http" if _is_loopback_host(host) else "https"
        api_url = f"{scheme}://{host}:{port}"

    timeout_raw = os.getenv("GG_TASK_CLIENT_TIMEOUT")
    timeout = float(timeout_raw) if timeout_raw is not None else 30.0

    return TaskClientSettings(api_url=api_url, api_key=api_key, timeout=timeout)


def _is_loopback_host(hostname: str | None) -> bool:
    if hostname is None:
        return False
    lowered = hostname.lower()
    if lowered in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        return ip_address(hostname).is_loopback
    except ValueError:
        return False


__all__ = ["TaskClientSettings", "load_task_client_settings"]
