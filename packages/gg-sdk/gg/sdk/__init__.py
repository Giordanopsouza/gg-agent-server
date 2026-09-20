"""Client-side agent SDK for gg-agent-server."""

from gg.sdk.agent_backend import (
    AgentBackend,
    AgentConfig,
    EventEmitter,
    PiAgentConfig,
    RunningAgentBackend,
    create_agent_backend,
)
from gg.sdk.conversation import Conversation
from gg.sdk.docker_workspace import DockerWorkspace, DockerWorkspaceError
from gg.sdk.domain import (
    ConversationRecord,
    ConversationStatus,
    Event,
    EventKind,
    MessageDeliveryStatus,
    MessageReceipt,
    SendMessageRequest,
    SocketReceiptFrame,
    StartConversationRequest,
    SteerMessageRequest,
)
from gg.sdk.event_log import (
    BaseState,
    EventLog,
    MessageReceiptStore,
    load_base_state,
    load_meta,
    save_base_state,
    save_meta,
)
from gg.sdk.exceptions import (
    AgentCancelledError,
    AgentControlError,
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
    MessageIdConflictError,
)
from gg.sdk.local_conversation import LocalConversation
from gg.sdk.local_workspace import CommandResult, LocalWorkspace
from gg.sdk.pi_agent import PiAgentSettings, PiRpcAgent
from gg.sdk.remote_conversation import RemoteConversation, RemoteEventSubscription
from gg.sdk.remote_workspace import RemoteWorkspace
from gg.sdk.runtime_workspace import RuntimeWorkspace
from gg.sdk.repository_profiles import RepositoryProfile, load_repository_profiles
from gg.sdk.task_execution import (
    AgentOutcome,
    CheckOutcome,
    CommandCapture,
    StartTaskExecutionRequest,
    TaskExecutionPhase,
    TaskExecutionRecord,
    TaskResultManifest,
)
from gg.sdk.tasks import CreateTaskRequest, TaskRecord, TaskState
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
    "AgentCancelledError",
    "AgentConfig",
    "AgentControlError",
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
    "Event",
    "EventKind",
    "EventLog",
    "EventEmitter",
    "InvalidConversationStateError",
    "LocalConversation",
    "LocalWorkspace",
    "PiAgentSettings",
    "PiAgentConfig",
    "PiRpcAgent",
    "RunningAgentBackend",
    "RemoteConversation",
    "RemoteEventSubscription",
    "RemoteWorkspace",
    "RuntimeWorkspace",
    "SendMessageRequest",
    "SocketReceiptFrame",
    "StartConversationRequest",
    "SteerMessageRequest",
    "MessageDeliveryStatus",
    "MessageIdConflictError",
    "MessageReceipt",
    "MessageReceiptStore",
    "AgentOutcome",
    "CheckOutcome",
    "CommandCapture",
    "CreateTaskRequest",
    "RepositoryProfile",
    "StartTaskExecutionRequest",
    "TaskExecutionPhase",
    "TaskExecutionRecord",
    "TaskRecord",
    "TaskResultManifest",
    "TaskState",
    "load_repository_profiles",
    "Observation",
    "Tool",
    "ToolNotFoundError",
    "ToolRegistry",
    "WriteFileTool",
    "default_tool_registry",
    "create_agent_backend",
    "load_base_state",
    "load_meta",
    "save_base_state",
    "save_meta",
]
