from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from gg.sdk.domain import Event, EventKind
from gg.sdk.local_workspace import LocalWorkspace


EventEmitter = Callable[[EventKind, dict[str, Any]], Event]


class AgentBackend(Protocol):
    """Run one agent turn against a local workspace."""

    def run(
        self,
        prompt: str,
        workspace: LocalWorkspace,
        emit: EventEmitter,
    ) -> None: ...
