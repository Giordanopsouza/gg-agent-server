"""Redact one sandbox credential from nested event and evidence values."""

from __future__ import annotations

from typing import Any


def redact_secret(value: Any, secret: str) -> Any:
    if isinstance(value, str):
        return value.replace(secret, "[REDACTED]")
    if isinstance(value, list):
        return [redact_secret(item, secret) for item in value]
    if isinstance(value, dict):
        return {
            redact_secret(key, secret): redact_secret(item, secret)
            for key, item in value.items()
        }
    return value
