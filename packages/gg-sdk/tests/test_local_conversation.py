from __future__ import annotations

from pathlib import Path

import pytest

from gg.sdk import (
    ConversationAlreadyRunningError,
    ConversationStatus,
    Event,
    EventKind,
    EventLog,
    InvalidConversationStateError,
    LocalConversation,
    LocalWorkspace,
    load_base_state,
)
from gg.sdk.agent_backend import EventEmitter


class RecordingBackend:
    def __init__(self) -> None:
        self.prompt: str | None = None
        self.workspace: LocalWorkspace | None = None

    def run(
        self,
        prompt: str,
        workspace: LocalWorkspace,
        emit: EventEmitter,
    ) -> None:
        self.prompt = prompt
        self.workspace = workspace
        action = emit(EventKind.ACTION, {"tool": "record", "args": {}})
        assert isinstance(action, Event)
        emit(EventKind.OBSERVATION, {"recorded": True})


# Sending a message writes one MESSAGE event without starting the agent.
def test_send_message_appends_event_and_stays_idle(tmp_path: Path) -> None:
    workspace = LocalWorkspace(working_dir=tmp_path / "work")
    conversation = LocalConversation(
        conversation_dir=tmp_path / "conv-1",
        workspace=workspace,
    )

    conversation.send_message("remember to buy milk")

    assert conversation.status == ConversationStatus.IDLE
    events = EventLog(tmp_path / "conv-1").list()
    assert len(events) == 1
    assert events[0].kind == EventKind.MESSAGE
    assert events[0].payload == {"text": "remember to buy milk"}


# The happy path writes NOTES.md, logs each event, and ends finished.
def test_run_writes_notes_and_finishes(tmp_path: Path) -> None:
    workspace = LocalWorkspace(working_dir=tmp_path / "work")
    conv_dir = tmp_path / "conv-1"
    conversation = LocalConversation(conversation_dir=conv_dir, workspace=workspace)

    conversation.send_message("first task")
    conversation.run()

    assert conversation.status == ConversationStatus.FINISHED
    notes = workspace.read_file("NOTES.md")
    assert notes == b"# Notes\n\nfirst task\n"

    events = EventLog(conv_dir).list()
    assert [event.kind for event in events] == [
        EventKind.MESSAGE,
        EventKind.STATUS,
        EventKind.ACTION,
        EventKind.OBSERVATION,
        EventKind.STATUS,
    ]
    assert events[0].payload == {"text": "first task"}
    assert events[1].payload == {"status": ConversationStatus.RUNNING}
    assert events[2].payload["tool"] == "write_file"
    assert events[3].payload["path"] == "NOTES.md"
    assert events[4].payload == {"status": ConversationStatus.FINISHED}

    state = load_base_state(conv_dir)
    assert state.status == ConversationStatus.FINISHED


def test_run_delegates_prompt_workspace_and_event_emission(tmp_path: Path) -> None:
    workspace = LocalWorkspace(working_dir=tmp_path / "work")
    backend = RecordingBackend()
    conversation = LocalConversation(
        conversation_dir=tmp_path / "conv-1",
        workspace=workspace,
        agent_backend=backend,
    )
    conversation.send_message("older prompt")
    conversation.send_message("latest prompt")

    conversation.run()

    assert backend.prompt == "latest prompt"
    assert backend.workspace is workspace
    events = conversation.list_events()
    assert [event.kind for event in events] == [
        EventKind.MESSAGE,
        EventKind.MESSAGE,
        EventKind.STATUS,
        EventKind.ACTION,
        EventKind.OBSERVATION,
        EventKind.STATUS,
    ]
    assert events[3].payload == {"tool": "record", "args": {}}
    assert events[4].payload == {"recorded": True}


# A run cannot start while the conversation is already running.
def test_second_run_while_running_raises(tmp_path: Path) -> None:
    workspace = LocalWorkspace(working_dir=tmp_path / "work")
    conversation = LocalConversation(
        conversation_dir=tmp_path / "conv-1",
        workspace=workspace,
    )
    conversation.send_message("go")

    conversation._status = ConversationStatus.RUNNING

    with pytest.raises(ConversationAlreadyRunningError):
        conversation.run()


# A finished conversation cannot run again.
def test_run_after_finished_raises(tmp_path: Path) -> None:
    workspace = LocalWorkspace(working_dir=tmp_path / "work")
    conversation = LocalConversation(
        conversation_dir=tmp_path / "conv-1",
        workspace=workspace,
    )
    conversation.send_message("go")
    conversation.run()

    with pytest.raises(InvalidConversationStateError, match="run"):
        conversation.run()


# A fresh EventLog can reload the persisted history after a "restart".
def test_event_log_survives_restart(tmp_path: Path) -> None:
    workspace = LocalWorkspace(working_dir=tmp_path / "work")
    conv_dir = tmp_path / "conv-1"
    conversation = LocalConversation(conversation_dir=conv_dir, workspace=workspace)
    conversation.send_message("persist me")
    conversation.run()

    reloaded = EventLog(conv_dir)
    kinds = [event.kind for event in reloaded.list()]

    assert EventKind.MESSAGE in kinds
    assert EventKind.ACTION in kinds
    assert EventKind.OBSERVATION in kinds
    assert EventKind.STATUS in kinds
