from __future__ import annotations

from pathlib import Path

import pytest

from gg.server import get_settings
from gg.server.config import reset_settings


@pytest.fixture(autouse=True)
def _isolate_settings(monkeypatch):
    """Each test gets a fresh cache and only the env vars it sets."""
    for key in (
        "GG_HOST",
        "GG_PORT",
        "GG_CONVERSATIONS_DIR",
        "GG_WORKSPACE_DIR",
        "GG_SESSION_API_KEYS",
    ):
        monkeypatch.delenv(key, raising=False)
    reset_settings()
    yield
    reset_settings()


def test_defaults_when_no_env() -> None:
    # - # No GG_* set: every field falls back to its default.
    settings = get_settings()
    assert settings.host == "127.0.0.1"
    assert settings.port == 8000
    assert settings.conversations_dir == Path("workspace/conversations")
    assert settings.workspace_dir == Path("workspace/project")
    assert settings.session_api_keys == []


def test_parses_all_gg_env_vars(monkeypatch) -> None:
    # - # Every GG_* var maps to the matching Settings field.
    monkeypatch.setenv("GG_HOST", "0.0.0.0")
    monkeypatch.setenv("GG_PORT", "9000")
    monkeypatch.setenv("GG_CONVERSATIONS_DIR", "/tmp/convos")
    monkeypatch.setenv("GG_WORKSPACE_DIR", "/tmp/work")
    monkeypatch.setenv("GG_SESSION_API_KEYS", "key-one, key-two ,key-three")

    settings = get_settings()
    assert settings.host == "0.0.0.0"
    assert settings.port == 9000
    assert settings.conversations_dir == Path("/tmp/convos")
    assert settings.workspace_dir == Path("/tmp/work")
    assert settings.session_api_keys == ["key-one", "key-two", "key-three"]


def test_missing_optional_keys_means_empty_session_api_keys(monkeypatch) -> None:
    # - # GG_SESSION_API_KEYS absent -> open server (empty list).
    monkeypatch.setenv("GG_HOST", "0.0.0.0")
    settings = get_settings()
    assert settings.session_api_keys == []


def test_invalid_port_fails_naming_the_variable(monkeypatch) -> None:
    # - # Non-integer port raises ValueError whose message names GG_PORT.
    monkeypatch.setenv("GG_PORT", "not-an-int")
    with pytest.raises(ValueError, match="GG_PORT"):
        get_settings()


def test_port_out_of_range_fails_naming_the_variable(monkeypatch) -> None:
    # - # Out-of-range port also names GG_PORT in the error.
    monkeypatch.setenv("GG_PORT", "70000")
    with pytest.raises(ValueError, match="GG_PORT"):
        get_settings()


def test_get_settings_is_cached_singleton(monkeypatch) -> None:
    # - # Second call returns the same object; env changes are ignored after cache.
    monkeypatch.setenv("GG_PORT", "8001")
    first = get_settings()
    monkeypatch.setenv("GG_PORT", "8002")
    second = get_settings()
    assert first is second
    assert second.port == 8001


def test_settings_is_frozen() -> None:
    # - # Frozen model: mutating any field raises, protecting the singleton.
    settings = get_settings()
    with pytest.raises(Exception):
        settings.port = 9999  # type: ignore[misc]


def test_session_api_keys_strips_whitespace_and_empties(monkeypatch) -> None:
    # - # "a,, b ," yields ["a", "b"]; stray commas do not create blank keys.
    monkeypatch.setenv("GG_SESSION_API_KEYS", "a,, b ,")
    settings = get_settings()
    assert settings.session_api_keys == ["a", "b"]
