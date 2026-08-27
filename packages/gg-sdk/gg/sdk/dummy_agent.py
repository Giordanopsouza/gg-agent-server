from __future__ import annotations

from typing import Any

from gg.sdk.agent_backend import EventEmitter
from gg.sdk.domain import EventKind
from gg.sdk.local_workspace import LocalWorkspace
from gg.sdk.tools import ToolRegistry, default_tool_registry


def plan_write_notes(*, user_message: str) -> dict[str, Any]:
    """Dummy agent: always one write_file action for NOTES.md."""

    return {
        "tool": "write_file",
        "args": {
            "path": "NOTES.md",
            "content": f"# Notes\n\n{user_message}\n",
        },
    }


class DummyAgentBackend:
    """Offline backend that preserves the original scripted agent behavior."""

    def __init__(self, tool_registry: ToolRegistry | None = None) -> None:
        self._tool_registry = tool_registry or default_tool_registry()

    def run(
        self,
        prompt: str,
        workspace: LocalWorkspace,
        emit: EventEmitter,
    ) -> None:
        action = plan_write_notes(user_message=prompt)
        emit(
            EventKind.ACTION,
            {"tool": action["tool"], "args": action["args"]},
        )
        observation = self._tool_registry.run(
            action["tool"],
            action["args"],
            workspace,
        )
        emit(EventKind.OBSERVATION, observation.payload)
