from __future__ import annotations


class ConversationError(Exception):
    """Base class for conversation state violations."""


class ConversationAlreadyRunningError(ConversationError):
    """run() was called while the conversation is already running."""

    def __init__(self) -> None:
        super().__init__("conversation is already running")


class InvalidConversationStateError(ConversationError):
    """An operation is not allowed in the current status."""

    def __init__(self, *, status: str, operation: str) -> None:
        self.status = status
        self.operation = operation
        super().__init__(f"cannot {operation} while status is {status}")
