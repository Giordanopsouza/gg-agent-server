from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from gg.sdk.agent_backend import AgentConfig, PiAgentConfig
from gg.sdk.domain import (
    ConversationRecord,
    ConversationStatus,
    Event,
    EventKind,
    MessageDeliveryStatus,
    MessageReceipt,
)
from gg.server.agent.agent_backend import (
    AgentBackend,
    RunningAgentBackend,
    create_agent_backend,
)
from gg.server.agent.event_log import (
    EventLog,
    MessageReceiptStore,
    load_base_state,
    load_meta,
    save_base_state,
    save_meta,
)
from gg.server.agent.exceptions import (
    AgentCancelledError,
    AgentControlError,
    AgentError,
    ConversationAlreadyRunningError,
    InvalidConversationStateError,
    MessageIdConflictError,
)
from gg.server.agent.local_workspace import LocalWorkspace


# (current status, operation) -> next status
_ALLOWED_TRANSITIONS: dict[tuple[ConversationStatus, str], ConversationStatus] = {
    (ConversationStatus.IDLE, "send_message"): ConversationStatus.IDLE,
    (ConversationStatus.IDLE, "run"): ConversationStatus.RUNNING,
    (ConversationStatus.RUNNING, "finish"): ConversationStatus.FINISHED,
    (ConversationStatus.RUNNING, "error"): ConversationStatus.ERROR,
    (ConversationStatus.RUNNING, "cancel"): ConversationStatus.CANCELLED,
}

PersistedEventListener = Callable[[Event], None]


class LocalConversation:
    """In-process conversation that persists events around an agent backend."""

    # Wire up workspace, event log, and on-disk meta; start in idle.
    def __init__(
        self,
        *,
        conversation_dir: Path | str,
        workspace: LocalWorkspace,
        conversation_id: str | None = None,
        agent: AgentConfig | None = None,
        agent_backend: AgentBackend | None = None,
        persisted_event_listener: PersistedEventListener | None = None,
    ) -> None:
        self.conversation_dir = Path(conversation_dir)
        self.workspace = workspace
        self._agent = agent or PiAgentConfig()
        self._agent_backend = agent_backend or create_agent_backend(self._agent)
        self._event_log = EventLog(self.conversation_dir)
        self._message_receipts = MessageReceiptStore(self.conversation_dir)
        self._persisted_event_listener = persisted_event_listener
        self._status = ConversationStatus.IDLE
        self._control_lock = threading.RLock()
        self._event_lock = threading.Lock()
        self._accepting_messages = False
        self._cancelling = False
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
        agent_backend: AgentBackend | None = None,
    ) -> LocalConversation:
        """Load an existing conversation from disk without resetting its state."""
        dir_path = Path(conversation_dir)
        meta = load_meta(dir_path)
        state = load_base_state(dir_path)
        ws = workspace or LocalWorkspace(working_dir=state.working_dir)
        obj = cls.__new__(cls)
        obj.conversation_dir = dir_path
        obj.workspace = ws
        obj._agent = state.agent
        obj._agent_backend = agent_backend or create_agent_backend(state.agent)
        obj._event_log = EventLog(dir_path)
        obj._message_receipts = MessageReceiptStore(dir_path)
        obj._persisted_event_listener = None
        obj._status = state.status
        obj._control_lock = threading.RLock()
        obj._event_lock = threading.Lock()
        obj._accepting_messages = False
        obj._cancelling = False
        obj.id = meta.id
        return obj

    # Expose the current conversation status (idle, running, finished, …).
    @property
    def status(self) -> ConversationStatus:
        return self._status

    # Record a user message in the event log; status stays idle until run().
    def send_message(self, text: str) -> Event:
        with self._control_lock:
            self._transition("send_message")
            return self._append_event(
                EventKind.MESSAGE,
                {"role": "user", "text": text},
            )

    def steer(self, message_id: str, text: str) -> MessageReceipt:
        """Durably accept and deliver one idempotent running-agent message."""
        with self._control_lock:
            existing = self._message_receipts.load(message_id)
            if existing is not None:
                if existing.content != text:
                    raise MessageIdConflictError(message_id)
                return existing
            if (
                self._status != ConversationStatus.RUNNING
                or not self._accepting_messages
            ):
                raise InvalidConversationStateError(
                    status=self._status,
                    operation="send a running-agent message",
                )
            if not isinstance(self._agent_backend, RunningAgentBackend):
                raise AgentControlError("agent backend does not support steering")

            receipt = MessageReceipt(
                id=message_id,
                content=text,
                status=MessageDeliveryStatus.ACCEPTED,
            )
            # Persist acceptance before forwarding. A crash after this point is
            # deliberately reported as uncertain, never healed by replay.
            self._message_receipts.save(receipt)
            self._append_event(
                EventKind.MESSAGE,
                {"role": "user", "text": text, "client_message_id": message_id},
            )
            try:
                delivered, detail = self._agent_backend.steer(text)
            except (AgentError, AgentControlError) as exc:
                return self._update_receipt(
                    receipt,
                    MessageDeliveryStatus.UNKNOWN,
                    str(exc),
                )
            return self._update_receipt(
                receipt,
                (
                    MessageDeliveryStatus.DELIVERED
                    if delivered
                    else MessageDeliveryStatus.FAILED
                ),
                detail,
            )

    def get_message_receipt(self, message_id: str) -> MessageReceipt | None:
        with self._control_lock:
            return self._message_receipts.load(message_id)

    def cancel(self) -> None:
        """Stop acceptance, cooperatively abort, then stop the process tree."""
        with self._control_lock:
            if self._status == ConversationStatus.CANCELLED or self._cancelling:
                return
            if self._status != ConversationStatus.RUNNING:
                raise InvalidConversationStateError(
                    status=self._status,
                    operation="cancel",
                )
            if not isinstance(self._agent_backend, RunningAgentBackend):
                raise AgentControlError("agent backend does not support cancellation")
            self._accepting_messages = False
            self._cancelling = True
        self._agent_backend.cancel()

    def list_events(self) -> list[Event]:
        """Return persisted events in seq order."""
        return self._event_log.list()

    def set_persisted_event_listener(
        self, listener: PersistedEventListener | None
    ) -> None:
        """Observe events after their durable append, without transport coupling."""
        self._persisted_event_listener = listener

    # Run the selected backend once, persisting every event it emits.
    def run(self) -> None:
        with self._control_lock:
            if self._status == ConversationStatus.RUNNING:
                raise ConversationAlreadyRunningError()
            self._transition("run")
            self._apply_status(ConversationStatus.RUNNING)
            self._accepting_messages = isinstance(
                self._agent_backend, RunningAgentBackend
            )
            if isinstance(self._agent_backend, RunningAgentBackend):
                self._agent_backend.set_settling_listener(self._begin_settling)

        user_message = self._latest_user_message()
        try:
            self._agent_backend.run(
                user_message,
                self.workspace,
                self._append_event,
            )
        except AgentCancelledError:
            with self._control_lock:
                self._transition("cancel")
                self._apply_status(ConversationStatus.CANCELLED)
            return
        except AgentError as exc:
            self._append_event(EventKind.ERROR, exc.to_event_payload())
            with self._control_lock:
                self._transition("error")
                self._apply_status(ConversationStatus.ERROR)
            raise
        finally:
            self._begin_settling()
            if isinstance(self._agent_backend, RunningAgentBackend):
                self._agent_backend.set_settling_listener(None)

        with self._control_lock:
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
            agent=self._agent,
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
        with self._event_lock:
            event = Event(seq=self._next_seq(), kind=kind, payload=payload)
            self._event_log.append(event)
        if self._persisted_event_listener is not None:
            try:
                self._persisted_event_listener(event)
            except Exception:
                # Live delivery is best-effort; callers can recover every
                # notification from the durable log using its sequence.
                pass
        return event

    def _begin_settling(self) -> None:
        """Close message acceptance at the backend's settlement boundary."""
        with self._control_lock:
            self._accepting_messages = False

    def _update_receipt(
        self,
        receipt: MessageReceipt,
        status: MessageDeliveryStatus,
        detail: str | None,
    ) -> MessageReceipt:
        updated = receipt.model_copy(
            update={
                "status": status,
                "detail": detail,
                "updated_at": datetime.now(UTC),
            }
        )
        self._message_receipts.save(updated)
        return updated

    # Find the most recent message event text for the selected backend to use.
    def _latest_user_message(self) -> str:
        for event in reversed(self._event_log.list()):
            role = event.payload.get("role")
            if event.kind == EventKind.MESSAGE and role in (None, "user"):
                text = event.payload.get("text")
                if isinstance(text, str):
                    return text
        return ""
