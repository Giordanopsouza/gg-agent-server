"""Control-plane HTTP client for sandbox task execution."""

from __future__ import annotations

from gg.runtime.modal_sandbox import SandboxConnection
from gg.sdk.task_execution import (
    StartTaskExecutionRequest,
    TaskExecutionRecord,
    TaskResultManifest,
)


class TaskSupervisorClient:
    """Start and inspect executions through the agent-server HTTP API."""

    def __init__(self, connection: SandboxConnection) -> None:
        self._connection = connection

    async def start(
        self, request: StartTaskExecutionRequest
    ) -> tuple[TaskExecutionRecord, int]:
        async with self._connection.http_client(timeout=30) as client:
            response = await client.post(
                "/api/task-executions/start",
                json=request.model_dump(mode="json"),
            )
            response.raise_for_status()
            return (
                TaskExecutionRecord.model_validate(response.json()),
                response.status_code,
            )

    async def get_execution(self, execution_id: str) -> TaskExecutionRecord:
        async with self._connection.http_client(timeout=30) as client:
            response = await client.get(f"/api/task-executions/{execution_id}")
            response.raise_for_status()
            return TaskExecutionRecord.model_validate(response.json())

    async def get_manifest(self, execution_id: str) -> TaskResultManifest:
        async with self._connection.http_client(timeout=30) as client:
            response = await client.get(f"/api/task-executions/{execution_id}/manifest")
            response.raise_for_status()
            return TaskResultManifest.model_validate(response.json())


__all__ = ["TaskSupervisorClient"]
