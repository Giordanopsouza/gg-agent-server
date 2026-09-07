from __future__ import annotations

from gg.sdk import (
    DummyAgentBackend,
    DummyAgentConfig,
    PiAgentConfig,
    PiRpcAgent,
    create_agent_backend,
)


def test_backend_factory_preserves_dummy_default() -> None:
    assert isinstance(create_agent_backend(DummyAgentConfig()), DummyAgentBackend)


def test_backend_factory_builds_pi_from_persisted_settings() -> None:
    backend = create_agent_backend(
        PiAgentConfig(model="test/model", timeout_seconds=23)
    )

    assert isinstance(backend, PiRpcAgent)
    assert backend.settings.provider == "openrouter"
    assert backend.settings.model == "test/model"
    assert backend.settings.timeout_seconds == 23
