from __future__ import annotations

from pathlib import Path

from gg.sdk import PiAgentConfig
from gg.server.agent import Conversation, LocalConversation, LocalWorkspace


def test_factory_selects_local_conversation(tmp_path: Path) -> None:
    workspace = LocalWorkspace(working_dir=tmp_path / "work")

    conversation = Conversation(
        workspace=workspace,
        conversation_dir=tmp_path / "conversation",
    )

    assert isinstance(conversation, LocalConversation)


def test_factory_forwards_pi_configuration_to_local_conversation(
    tmp_path: Path,
) -> None:
    agent = PiAgentConfig(model="test/model", timeout_seconds=29)

    conversation = Conversation(
        workspace=LocalWorkspace(working_dir=tmp_path / "work"),
        conversation_dir=tmp_path / "conversation",
        agent=agent,
    )

    assert isinstance(conversation, LocalConversation)
    assert conversation._agent == agent
