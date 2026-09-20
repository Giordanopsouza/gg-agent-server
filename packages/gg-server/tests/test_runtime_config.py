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


def test_runtime_settings_default_allowlist_is_empty() -> None:
    settings = RuntimeSettings(api_key="control-secret")
    assert settings.repository_allowlist == ()
    assert settings.task_db_path == "gg-tasks.sqlite"
    assert settings.max_prompt_chars > 0


def test_runtime_settings_normalizes_allowlist() -> None:
    settings = RuntimeSettings(
        api_key="control-secret",
        repository_allowlist=(" owner/name ", "org/repo", "owner/name", ""),
    )
    assert settings.repository_allowlist == ("owner/name", "org/repo")


def test_runtime_settings_rejects_blank_task_db_path() -> None:
    with pytest.raises(ValidationError, match="task_db_path must not be empty"):
        RuntimeSettings(api_key="control-secret", task_db_path="   ")


def test_load_settings_reads_task_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_runtime_env(monkeypatch)
    monkeypatch.setenv("GG_RUNTIME_API_KEY", "control-secret")
    monkeypatch.setenv("GG_TASK_DB_PATH", "/tmp/gg-tasks.sqlite")
    monkeypatch.setenv("GG_REPOSITORY_ALLOWLIST", "owner/one, org/two , owner/one")
    monkeypatch.setenv("GG_MAX_PROMPT_CHARS", "1234")

    settings = load_settings()

    assert settings.task_db_path == "/tmp/gg-tasks.sqlite"
    assert settings.repository_allowlist == ("owner/one", "org/two")
    assert settings.max_prompt_chars == 1234
