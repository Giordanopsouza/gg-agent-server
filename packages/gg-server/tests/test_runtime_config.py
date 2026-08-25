from __future__ import annotations

import pytest
from pydantic import ValidationError

from gg.runtime.config import RuntimeSettings, load_settings


_RUNTIME_ENV = (
    "GG_RUNTIME_API_KEY",
    "GG_RUNTIME_HOST",
    "GG_RUNTIME_IMAGE",
    "GG_RUNTIME_PORT",
)


def _clear_runtime_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _RUNTIME_ENV:
        monkeypatch.delenv(name, raising=False)


def test_runtime_settings_load_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_runtime_env(monkeypatch)
    monkeypatch.setenv("GG_RUNTIME_API_KEY", "control-secret")
    monkeypatch.setenv("GG_RUNTIME_HOST", "0.0.0.0")
    monkeypatch.setenv("GG_RUNTIME_PORT", "9000")
    monkeypatch.setenv("GG_RUNTIME_IMAGE", "custom-agent:dev")

    settings = load_settings()

    assert settings.api_key == "control-secret"
    assert settings.host == "0.0.0.0"
    assert settings.port == 9000
    assert settings.image == "custom-agent:dev"


def test_runtime_api_key_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_runtime_env(monkeypatch)

    with pytest.raises(ValueError, match="GG_RUNTIME_API_KEY must be set"):
        load_settings()


@pytest.mark.parametrize("api_key", ["", "   ", " secret"])
def test_runtime_settings_reject_invalid_control_keys(api_key: str) -> None:
    with pytest.raises(ValidationError, match="api_key must be non-empty"):
        RuntimeSettings(api_key=api_key)
