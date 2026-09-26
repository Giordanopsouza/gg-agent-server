from __future__ import annotations

import pytest

from gg.sdk import EventKind
from gg.server.agent import local_conversation as local_conversation_module
from gg.server.agent.agent_backend import EventEmitter
from gg.server.agent.local_workspace import LocalWorkspace


class ScriptedBackend:
    """Offline stand-in that emits one action and one observation."""

    def run(
        self,
        prompt: str,
        workspace: LocalWorkspace,
        emit: EventEmitter,
    ) -> None:
        emit(EventKind.ACTION, {"tool": "write", "args": {}})
        emit(EventKind.OBSERVATION, {"result": "ok"})


@pytest.fixture
def scripted_agent(monkeypatch: pytest.MonkeyPatch) -> ScriptedBackend:
    backend = ScriptedBackend()
    monkeypatch.setattr(
        local_conversation_module,
        "create_agent_backend",
        lambda config: backend,
    )
    return backend
