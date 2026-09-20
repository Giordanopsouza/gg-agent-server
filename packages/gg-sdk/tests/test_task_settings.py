from __future__ import annotations

import pytest

from gg.sdk.task_settings import TaskClientSettings, load_task_client_settings


def test_http_url_requires_loopback() -> None:
    with pytest.raises(ValueError, match="insecure http"):
        TaskClientSettings(api_url="http://example.com", api_key="secret")


def test_load_settings_from_host_and_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GG_RUNTIME_API_KEY", "control-secret")
    monkeypatch.delenv("GG_TASK_API_URL", raising=False)
    monkeypatch.setenv("GG_RUNTIME_HOST", "127.0.0.1")
    monkeypatch.setenv("GG_RUNTIME_PORT", "8001")

    settings = load_task_client_settings()

    assert settings.api_url == "http://127.0.0.1:8001"
    assert settings.api_key == "control-secret"


def test_explicit_task_api_url_overrides_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GG_RUNTIME_API_KEY", "control-secret")
    monkeypatch.setenv("GG_TASK_API_URL", "https://tasks.example")

    settings = load_task_client_settings()

    assert settings.api_url == "https://tasks.example"
