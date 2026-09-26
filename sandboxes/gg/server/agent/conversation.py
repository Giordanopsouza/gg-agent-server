from __future__ import annotations

from pathlib import Path

from gg.sdk.agent_backend import AgentConfig
from gg.server.agent.local_conversation import LocalConversation
from gg.server.agent.local_workspace import LocalWorkspace


class Conversation:
    """Start a local conversation against a workspace on this machine."""

    def __new__(
        cls,
        *,
        workspace: LocalWorkspace,
        conversation_dir: Path | str,
        conversation_id: str | None = None,
        agent: AgentConfig | None = None,
    ) -> LocalConversation:
        return LocalConversation(
            conversation_dir=conversation_dir,
            workspace=workspace,
            conversation_id=conversation_id,
            agent=agent,
        )
