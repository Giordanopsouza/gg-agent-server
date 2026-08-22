from __future__ import annotations

from pathlib import Path

import pytest

from gg.sdk import (
    ConversationAlreadyRunningError,
    ConversationStatus,
    EventKind,
    EventLog,
    InvalidConversationStateError,
    LocalConversation,
    LocalWorkspace,
    load_base_state,
)


# Sending a message writes one MESSAGE event to disk but does not start the agent (status stays idle).
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


# The happy path: send_message then run() writes NOTES.md, logs all events in order, and ends finished.
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


# You cannot call run() again while status is already running — it raises ConversationAlreadyRunningError.
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


# After a run finishes, calling run() again is illegal — it raises InvalidConversationStateError.
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


# Events are stored on disk, so a fresh EventLog object can reload the full history after a "restart".
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
