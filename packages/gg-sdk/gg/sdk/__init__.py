"""Client-side agent SDK for gg-agent-server."""

from gg.sdk.domain import (
    ConversationRecord,
    ConversationStatus,
    Event,
    EventKind,
)
from gg.sdk.event_log import (
    BaseState,
    EventLog,
    load_base_state,
    load_meta,
    save_base_state,
    save_meta,
)
from gg.sdk.local_workspace import CommandResult, LocalWorkspace


__all__ = [
    "BaseState",
    "CommandResult",
    "ConversationRecord",
    "ConversationStatus",
    "Event",
    "EventKind",
    "EventLog",
    "LocalWorkspace",
    "load_base_state",
    "load_meta",
    "save_base_state",
    "save_meta",
]