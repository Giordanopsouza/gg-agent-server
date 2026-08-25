from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from gg.sdk.domain import ConversationRecord, ConversationStatus, Event


EVENTS_DIR = "events"
META_FILE = "meta.json"
BASE_STATE_FILE = "base_state.json"


class BaseState(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: ConversationStatus
    working_dir: str


# Ensure the conversation directory exists and return it as a Path
def _ensure_conversation_dir(conversation_dir: Path | str) -> Path:
    path = Path(conversation_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


# Write ConversationRecord to meta.json
def save_meta(conversation_dir: Path | str, record: ConversationRecord) -> None:
    path = _ensure_conversation_dir(conversation_dir) / META_FILE
    path.write_text(record.model_dump_json(), encoding="utf-8")


# Read ConversationRecord from meta.json
def load_meta(conversation_dir: Path | str) -> ConversationRecord:
    path = Path(conversation_dir) / META_FILE
    return ConversationRecord.model_validate_json(path.read_text(encoding="utf-8"))


# Write status and working_dir to base_state.json
def save_base_state(
    conversation_dir: Path | str,
    *,
    status: ConversationStatus,
    working_dir: str,
) -> None:
    state = BaseState(status=status, working_dir=working_dir)
    path = _ensure_conversation_dir(conversation_dir) / BASE_STATE_FILE
    path.write_text(state.model_dump_json(), encoding="utf-8")


# Read status and working_dir from base_state.json
def load_base_state(conversation_dir: Path | str) -> BaseState:
    path = Path(conversation_dir) / BASE_STATE_FILE
    return BaseState.model_validate_json(path.read_text(encoding="utf-8"))


# Build the event filename: event-00001-{id}.json
def _event_filename(event: Event) -> str:
    return f"event-{event.seq:05d}-{event.id}.json"


class EventLog:
    """Append-only event log backed by one JSON file per event."""

    # Store the conversation path and create events/ if missing
    def __init__(self, conversation_dir: Path | str) -> None:
        self.conversation_dir = Path(conversation_dir)
        self.events_dir = self.conversation_dir / EVENTS_DIR
        self.events_dir.mkdir(parents=True, exist_ok=True)

    # Write one event as a JSON file under events/
    def append(self, event: Event) -> None:
        path = self.events_dir / _event_filename(event)
        path.write_text(event.model_dump_json(), encoding="utf-8")

    # Read all events from disk and return them sorted by seq
    def list(self) -> list[Event]:
        events: list[Event] = []
        for path in sorted(self.events_dir.glob("event-*.json")):
            events.append(
                Event.model_validate_json(path.read_text(encoding="utf-8"))
            )
        events.sort(key=lambda event: event.seq)
        return events
