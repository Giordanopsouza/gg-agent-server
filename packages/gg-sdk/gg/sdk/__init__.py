"""Client-side agent SDK for gg-agent-server."""

from gg.sdk.agent_backend import AgentBackend, EventEmitter
from gg.sdk.conversation import Conversation
from gg.sdk.docker_workspace import DockerWorkspace, DockerWorkspaceError
from gg.sdk.domain import (
    ConversationRecord,
    ConversationStatus,
    Event,
    EventKind,
    SendMessageRequest,
    StartConversationRequest,
)
from gg.sdk.dummy_agent import DummyAgentBackend
from gg.sdk.event_log import (
    BaseState,
    EventLog,
    load_base_state,
    load_meta,
    save_base_state,
    save_meta,
)
from gg.sdk.exceptions import (
    AgentError,
    AgentProcessError,
    AgentPromptError,
    AgentProtocolError,
    AgentStartupError,
    AgentTimeoutError,
    ConversationAlreadyRunningError,
    ConversationError,
    ConversationNotFoundError,
    InvalidConversationStateError,
)
from gg.sdk.local_conversation import LocalConversation
from gg.sdk.local_workspace import CommandResult, LocalWorkspace
from gg.sdk.pi_agent import PiAgentSettings, PiRpcAgent
from gg.sdk.remote_conversation import RemoteConversation, RemoteEventSubscription
from gg.sdk.remote_workspace import RemoteWorkspace
from gg.sdk.runtime_workspace import RuntimeWorkspace
from gg.sdk.tools import (
    Observation,
    Tool,
    ToolNotFoundError,
    ToolRegistry,
    WriteFileTool,
    default_tool_registry,
)


__all__ = [
    "AgentBackend",
    "AgentError",
    "AgentProcessError",
    "AgentPromptError",
    "AgentProtocolError",
    "AgentStartupError",
    "AgentTimeoutError",
    "BaseState",
    "CommandResult",
    "Conversation",
    "ConversationAlreadyRunningError",
    "ConversationError",
    "ConversationNotFoundError",
    "ConversationRecord",
    "ConversationStatus",
    "DockerWorkspace",
    "DockerWorkspaceError",
    "DummyAgentBackend",
    "Event",
    "EventKind",
    "EventLog",
    "EventEmitter",
    "InvalidConversationStateError",
    "LocalConversation",
    "LocalWorkspace",
    "PiAgentSettings",
    "PiRpcAgent",
    "RemoteConversation",
    "RemoteEventSubscription",
    "RemoteWorkspace",
    "RuntimeWorkspace",
    "SendMessageRequest",
    "StartConversationRequest",
    "Observation",
    "Tool",
    "ToolNotFoundError",
    "ToolRegistry",
    "WriteFileTool",
    "default_tool_registry",
    "load_base_state",
    "load_meta",
    "save_base_state",
    "save_meta",
]
