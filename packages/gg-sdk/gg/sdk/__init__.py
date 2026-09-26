"""Python task client and shared HTTP contracts."""

from gg.sdk.agent_backend import AgentConfig, PiAgentConfig
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
from gg.sdk.publication import PublicationRecord, PublicationRequest, PublicationState
from gg.sdk.remote_workspace import RemoteWorkspace
from gg.sdk.task_client import (
    SubmitResponse,
    TaskClient,
    TaskClientError,
    TaskEventSubscription,
    TaskNotFoundError,
)
from gg.sdk.task_execution import (
    AgentOutcome,
    CheckOutcome,
    CommandCapture,
    StartTaskExecutionRequest,
    TaskExecutionPhase,
    TaskExecutionRecord,
    TaskResultManifest,
)
from gg.sdk.task_settings import TaskClientSettings, load_task_client_settings
from gg.sdk.task_supervision import (
    RetryTaskRequest,
    TaskEventCopy,
    TaskMessageRequest,
    TaskResultRecord,
)
from gg.sdk.tasks import CreateTaskRequest, TaskRecord, TaskState


__all__ = [
    "AgentConfig",
    "PiAgentConfig",
    "ConversationRecord",
    "ConversationStatus",
    "Event",
    "EventKind",
    "MessageDeliveryStatus",
    "MessageReceipt",
    "SendMessageRequest",
    "SocketReceiptFrame",
    "StartConversationRequest",
    "SteerMessageRequest",
    "PublicationRecord",
    "PublicationRequest",
    "PublicationState",
    "RemoteWorkspace",
    "SubmitResponse",
    "TaskClient",
    "TaskClientError",
    "TaskEventSubscription",
    "TaskNotFoundError",
    "AgentOutcome",
    "CheckOutcome",
    "CommandCapture",
    "StartTaskExecutionRequest",
    "TaskExecutionPhase",
    "TaskExecutionRecord",
    "TaskResultManifest",
    "TaskClientSettings",
    "load_task_client_settings",
    "RetryTaskRequest",
    "TaskEventCopy",
    "TaskMessageRequest",
    "TaskResultRecord",
    "CreateTaskRequest",
    "TaskRecord",
    "TaskState",
]
