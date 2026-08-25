from __future__ import annotations

from pathlib import Path

import httpx

from gg.sdk.local_conversation import LocalConversation
from gg.sdk.local_workspace import LocalWorkspace
from gg.sdk.remote_conversation import RemoteConversation
from gg.sdk.remote_workspace import RemoteWorkspace
from gg.sdk.tools import ToolRegistry


class Conversation:
    """Choose a local or remote conversation from the workspace transport."""

    def __new__(
        cls,
        *,
        workspace: LocalWorkspace | RemoteWorkspace,
        conversation_dir: Path | str | None = None,
        conversation_id: str | None = None,
        tool_registry: ToolRegistry | None = None,
        client: httpx.Client | None = None,
    ) -> LocalConversation | RemoteConversation:
        if isinstance(workspace, RemoteWorkspace):
            return RemoteConversation(
                workspace=workspace,
                conversation_id=conversation_id,
                client=client,
            )

        if conversation_dir is None:
            raise ValueError("conversation_dir is required for a local conversation")
        return LocalConversation(
            conversation_dir=conversation_dir,
            workspace=workspace,
            tool_registry=tool_registry,
            conversation_id=conversation_id,
        )
