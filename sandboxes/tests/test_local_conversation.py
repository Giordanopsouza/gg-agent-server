from __future__ import annotations

import threading
from pathlib import Path

import pytest

from gg.sdk import (
    ConversationStatus,
    Event,
    EventKind,
    MessageDeliveryStatus,
    MessageReceipt,
)
from gg.server.agent import (
    AgentCancelledError,
    ConversationAlreadyRunningError,
    EventLog,
    InvalidConversationStateError,
    LocalConversation,
    LocalWorkspace,
    MessageIdConflictError,
    MessageReceiptStore,
    load_base_state,
)
from gg.server.agent.agent_backend import EventEmitter


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


class ControllableBackend:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()
        self.listener = None
        self.messages: list[str] = []
        self.cancelled = False

    def set_settling_listener(self, listener):  # noqa: ANN001
        self.listener = listener

    def run(
        self,
        prompt: str,
        workspace: LocalWorkspace,
        emit: EventEmitter,
    ) -> None:
        self.started.set()
        assert self.release.wait(timeout=3)
        if self.listener is not None:
            self.listener()
        if self.cancelled:
            raise AgentCancelledError("cancelled")

    def steer(self, message: str) -> tuple[bool, str | None]:
        self.messages.append(message)
        return True, None

    def cancel(self) -> None:
        self.cancelled = True
        self.release.set()


class BlockingSteerBackend(ControllableBackend):
    def __init__(self) -> None:
        super().__init__()
        self.steer_started = threading.Event()
        self.acknowledge = threading.Event()

    def steer(self, message: str) -> tuple[bool, str | None]:
        self.steer_started.set()
        assert self.acknowledge.wait(timeout=2)
        return super().steer(message)


class InspectingBackend(ControllableBackend):
    def __init__(self, conversation_dir: Path) -> None:
        super().__init__()
        self.store = MessageReceiptStore(conversation_dir)
        self.observed_status: MessageDeliveryStatus | None = None

    def steer(self, message: str) -> tuple[bool, str | None]:
        receipt = self.store.load("client-1")
        assert receipt is not None
        self.observed_status = receipt.status
        return False, "Pi rejected steer"


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
    assert events[0].payload == {"role": "user", "text": "remember to buy milk"}


# The happy path logs each event and ends finished.
def test_run_finishes_and_persists_events(tmp_path: Path) -> None:
    workspace = LocalWorkspace(working_dir=tmp_path / "work")
    conv_dir = tmp_path / "conv-1"
    backend = RecordingBackend()
    conversation = LocalConversation(
        conversation_dir=conv_dir,
        workspace=workspace,
        agent_backend=backend,
    )

    conversation.send_message("first task")
    conversation.run()

    assert conversation.status == ConversationStatus.FINISHED
    assert backend.prompt == "first task"

    events = EventLog(conv_dir).list()
    assert [event.kind for event in events] == [
        EventKind.MESSAGE,
        EventKind.STATUS,
        EventKind.ACTION,
        EventKind.OBSERVATION,
        EventKind.STATUS,
    ]
    assert events[0].payload == {"role": "user", "text": "first task"}
    assert events[1].payload == {"status": ConversationStatus.RUNNING}
    assert events[2].payload == {"tool": "record", "args": {}}
    assert events[3].payload == {"recorded": True}
    assert events[4].payload == {"status": ConversationStatus.FINISHED}

    state = load_base_state(conv_dir)
    assert state.status == ConversationStatus.FINISHED


def test_persisted_listener_observes_each_event_after_append(tmp_path: Path) -> None:
    observed: list[Event] = []
    conv_dir = tmp_path / "conv-1"
    conversation = LocalConversation(
        conversation_dir=conv_dir,
        workspace=LocalWorkspace(working_dir=tmp_path / "work"),
        agent_backend=RecordingBackend(),
        persisted_event_listener=lambda event: observed.append(event),
    )

    conversation.send_message("persist before notify")
    conversation.run()

    assert observed == EventLog(conv_dir).list()


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


def test_latest_prompt_ignores_assistant_but_accepts_legacy_message(
    tmp_path: Path,
) -> None:
    workspace = LocalWorkspace(working_dir=tmp_path / "work")
    backend = RecordingBackend()
    conversation = LocalConversation(
        conversation_dir=tmp_path / "conv-1",
        workspace=workspace,
        agent_backend=backend,
    )
    conversation._event_log.append(
        Event(seq=1, kind=EventKind.MESSAGE, payload={"text": "legacy user"})
    )
    conversation._event_log.append(
        Event(
            seq=2,
            kind=EventKind.MESSAGE,
            payload={"role": "assistant", "text": "not the prompt"},
        )
    )

    conversation.run()

    assert backend.prompt == "legacy user"


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
        agent_backend=RecordingBackend(),
    )
    conversation.send_message("go")
    conversation.run()

    with pytest.raises(InvalidConversationStateError, match="run"):
        conversation.run()


# A fresh EventLog can reload the persisted history after a "restart".
def test_event_log_survives_restart(tmp_path: Path) -> None:
    workspace = LocalWorkspace(working_dir=tmp_path / "work")
    conv_dir = tmp_path / "conv-1"
    conversation = LocalConversation(
        conversation_dir=conv_dir,
        workspace=workspace,
        agent_backend=RecordingBackend(),
    )
    conversation.send_message("persist me")
    conversation.run()

    reloaded = EventLog(conv_dir)
    kinds = [event.kind for event in reloaded.list()]

    assert EventKind.MESSAGE in kinds
    assert EventKind.ACTION in kinds
    assert EventKind.OBSERVATION in kinds
    assert EventKind.STATUS in kinds


def test_running_message_is_idempotent_and_persists_delivery_receipt(
    tmp_path: Path,
) -> None:
    backend = ControllableBackend()
    conversation = LocalConversation(
        conversation_dir=tmp_path / "conv-1",
        workspace=LocalWorkspace(working_dir=tmp_path / "work"),
        agent_backend=backend,
    )
    conversation.send_message("start")
    run_thread = threading.Thread(target=conversation.run)
    run_thread.start()
    assert backend.started.wait(timeout=1)

    first = conversation.steer("client-1", "change direction")
    duplicate = conversation.steer("client-1", "change direction")
    with pytest.raises(MessageIdConflictError):
        conversation.steer("client-1", "different content")

    assert first.status == MessageDeliveryStatus.DELIVERED
    assert duplicate == first
    assert backend.messages == ["change direction"]
    assert conversation.get_message_receipt("client-1") == first

    backend.release.set()
    run_thread.join(timeout=2)
    assert not run_thread.is_alive()
    with pytest.raises(InvalidConversationStateError):
        conversation.steer("client-2", "too late")

    reopened = LocalConversation.open(conversation_dir=tmp_path / "conv-1")
    assert reopened.get_message_receipt("client-1") == first


def test_cancel_closes_acceptance_and_settles_cancelled(tmp_path: Path) -> None:
    backend = ControllableBackend()
    conversation = LocalConversation(
        conversation_dir=tmp_path / "conv-1",
        workspace=LocalWorkspace(working_dir=tmp_path / "work"),
        agent_backend=backend,
    )
    conversation.send_message("start")
    run_thread = threading.Thread(target=conversation.run)
    run_thread.start()
    assert backend.started.wait(timeout=1)

    conversation.cancel()
    run_thread.join(timeout=2)

    assert conversation.status == ConversationStatus.CANCELLED
    assert not run_thread.is_alive()
    with pytest.raises(InvalidConversationStateError):
        conversation.steer("after-cancel", "too late")


def test_acceptance_is_persisted_before_pi_and_explicit_rejection_is_failed(
    tmp_path: Path,
) -> None:
    conversation_dir = tmp_path / "conv-1"
    backend = InspectingBackend(conversation_dir)
    conversation = LocalConversation(
        conversation_dir=conversation_dir,
        workspace=LocalWorkspace(working_dir=tmp_path / "work"),
        agent_backend=backend,
    )
    conversation.send_message("start")
    run_thread = threading.Thread(target=conversation.run)
    run_thread.start()
    assert backend.started.wait(timeout=1)

    receipt = conversation.steer("client-1", "rejected")
    backend.release.set()
    run_thread.join(timeout=2)

    assert backend.observed_status == MessageDeliveryStatus.ACCEPTED
    assert receipt.status == MessageDeliveryStatus.FAILED


def test_message_winning_settlement_race_is_accepted_before_finalization(
    tmp_path: Path,
) -> None:
    backend = BlockingSteerBackend()
    conversation = LocalConversation(
        conversation_dir=tmp_path / "conv-1",
        workspace=LocalWorkspace(working_dir=tmp_path / "work"),
        agent_backend=backend,
    )
    conversation.send_message("start")
    run_thread = threading.Thread(target=conversation.run)
    run_thread.start()
    assert backend.started.wait(timeout=1)

    result: list[MessageReceipt] = []
    steer_thread = threading.Thread(
        target=lambda: result.append(conversation.steer("race-1", "accepted"))
    )
    steer_thread.start()
    assert backend.steer_started.wait(timeout=1)
    backend.release.set()
    backend.acknowledge.set()
    steer_thread.join(timeout=2)
    run_thread.join(timeout=2)

    assert result[0].status == MessageDeliveryStatus.DELIVERED
    assert conversation.status == ConversationStatus.FINISHED
    with pytest.raises(InvalidConversationStateError):
        conversation.steer("race-2", "rejected")
