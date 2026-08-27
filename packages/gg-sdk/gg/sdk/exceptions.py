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


class ConversationNotFoundError(ConversationError):
    """A conversation id has no on-disk catalog entry."""

    def __init__(self, conversation_id: str) -> None:
        self.conversation_id = conversation_id
        super().__init__(f"conversation not found: {conversation_id}")


class AgentError(Exception):
    """A sanitized failure raised by an agent backend."""

    code = "agent_error"

    def to_event_payload(self) -> dict[str, str]:
        return {"type": self.code, "message": str(self)}


class AgentStartupError(AgentError):
    """The selected backend cannot start in the current environment."""

    code = "agent_startup_error"


class AgentPromptError(AgentError):
    """The backend rejected the correlated prompt command."""

    code = "agent_prompt_error"


class AgentProtocolError(AgentError):
    """The backend emitted an invalid protocol message."""

    code = "agent_protocol_error"


class AgentProcessError(AgentError):
    """The backend process exited or failed before settling."""

    code = "agent_process_error"


class AgentTimeoutError(AgentError):
    """The backend did not settle within its configured deadline."""

    code = "agent_timeout_error"
