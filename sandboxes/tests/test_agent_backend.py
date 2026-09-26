from __future__ import annotations

from gg.sdk import PiAgentConfig
from gg.server.agent import PiRpcAgent, create_agent_backend


def test_backend_factory_builds_pi_from_persisted_settings() -> None:
    backend = create_agent_backend(
        PiAgentConfig(model="test/model", timeout_seconds=23)
    )

    assert isinstance(backend, PiRpcAgent)
    assert backend.settings.provider == "openrouter"
    assert backend.settings.model == "test/model"
    assert backend.settings.timeout_seconds == 23


def test_backend_factory_defaults_to_pi() -> None:
    config = PiAgentConfig()
    backend = create_agent_backend(config)

    assert isinstance(backend, PiRpcAgent)
    assert config.model == backend.settings.model == "z-ai/glm-5.3-flashx"
