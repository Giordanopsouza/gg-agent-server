from __future__ import annotations

from pathlib import Path
from typing import Any

from gg.sdk.domain import ConversationRecord, ConversationStatus, Event, EventKind
from gg.sdk.dummy_agent import plan_write_notes
from gg.sdk.event_log import (
    EventLog,
    load_base_state,
    load_meta,
    save_base_state,
    save_meta,
)
from gg.sdk.exceptions import (
    ConversationAlreadyRunningError,
    InvalidConversationStateError,
)
from gg.sdk.local_workspace import LocalWorkspace
from gg.sdk.tools import ToolRegistry, default_tool_registry


# (current status, operation) -> next status
_ALLOWED_TRANSITIONS: dict[tuple[ConversationStatus, str], ConversationStatus] = {
    (ConversationStatus.IDLE, "send_message"): ConversationStatus.IDLE,
    (ConversationStatus.IDLE, "run"): ConversationStatus.RUNNING,
    (ConversationStatus.RUNNING, "finish"): ConversationStatus.FINISHED,
}


class LocalConversation:
    """In-process conversation: event log, workspace, and a dummy agent loop."""

    # Wire up workspace, event log, and on-disk meta; start in idle.
    def __init__(
        self,
        *,
        conversation_dir: Path | str,
        workspace: LocalWorkspace,
        tool_registry: ToolRegistry | None = None,
        conversation_id: str | None = None,
    ) -> None:
        self.conversation_dir = Path(conversation_dir)
        self.workspace = workspace
        self._tool_registry = tool_registry or default_tool_registry()
        self._event_log = EventLog(self.conversation_dir)
        self._status = ConversationStatus.IDLE
        self.id = conversation_id or str(self.conversation_dir.name)

        save_meta(
            self.conversation_dir,
            ConversationRecord(
                id=self.id,
                status=self._status,
                working_dir=str(self.workspace.working_dir),
            ),
        )
        self._persist_status()

    @classmethod
    def open(
        cls,
        *,
        conversation_dir: Path | str,
        workspace: LocalWorkspace | None = None,
        tool_registry: ToolRegistry | None = None,
    ) -> LocalConversation:
        """Load an existing conversation from disk without resetting its state."""
        dir_path = Path(conversation_dir)
        meta = load_meta(dir_path)
        state = load_base_state(dir_path)
        ws = workspace or LocalWorkspace(working_dir=state.working_dir)
        obj = cls.__new__(cls)
        obj.conversation_dir = dir_path
        obj.workspace = ws
        obj._tool_registry = tool_registry or default_tool_registry()
        obj._event_log = EventLog(dir_path)
        obj._status = state.status
        obj.id = meta.id
        return obj

    # Expose the current conversation status (idle, running, finished, …).
    @property
    def status(self) -> ConversationStatus:
        return self._status

    # Record a user message in the event log; status stays idle until run().
    def send_message(self, text: str) -> None:
        self._transition("send_message")
        self._append_event(EventKind.MESSAGE, {"text": text})

    # Run the dummy agent once: plan action, execute tool, then finish.
    def run(self) -> None:
        if self._status == ConversationStatus.RUNNING:
            raise ConversationAlreadyRunningError()
        self._transition("run")
        self._apply_status(ConversationStatus.RUNNING)

        user_message = self._latest_user_message()
        action = plan_write_notes(user_message=user_message)

        self._append_event(
            EventKind.ACTION,
            {"tool": action["tool"], "args": action["args"]},
        )
        observation = self._tool_registry.run(
            action["tool"],
            action["args"],
            self.workspace,
        )
        self._append_event(EventKind.OBSERVATION, observation.payload)

        self._transition("finish")
        self._apply_status(ConversationStatus.FINISHED)

    # Reject operations that are not allowed from the current status.
    def _transition(self, operation: str) -> None:
        key = (self._status, operation)
        if key not in _ALLOWED_TRANSITIONS:
            raise InvalidConversationStateError(
                status=self._status,
                operation=operation,
            )

    # Update in-memory status, persist it, and append a status event.
    def _apply_status(self, status: ConversationStatus) -> None:
        self._status = status
        self._persist_status()
        self._append_event(EventKind.STATUS, {"status": self._status})

    # Write status and working_dir to base_state.json and meta.json.
    def _persist_status(self) -> None:
        save_base_state(
            self.conversation_dir,
            status=self._status,
            working_dir=str(self.workspace.working_dir),
        )
        save_meta(
            self.conversation_dir,
            ConversationRecord(
                id=self.id,
                status=self._status,
                working_dir=str(self.workspace.working_dir),
            ),
        )

    # Return the next event sequence number (one greater than the last on disk).
    def _next_seq(self) -> int:
        events = self._event_log.list()
        if not events:
            return 1
        return events[-1].seq + 1

    # Build an event with the next seq and append it to the event log.
    def _append_event(self, kind: EventKind, payload: dict[str, Any]) -> Event:
        event = Event(seq=self._next_seq(), kind=kind, payload=payload)
        self._event_log.append(event)
        return event

    # Find the most recent message event text for the dummy agent to use.
    def _latest_user_message(self) -> str:
        for event in reversed(self._event_log.list()):
            if event.kind == EventKind.MESSAGE:
                text = event.payload.get("text")
                if isinstance(text, str):
                    return text
        return ""
