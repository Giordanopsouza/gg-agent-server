"""HTTP routes for sandbox task execution."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status

from gg.sdk.task_execution import (
    StartTaskExecutionRequest,
    TaskExecutionRecord,
    TaskResultManifest,
)
from gg.server.dependencies import get_task_supervisor_service
from gg.server.task_supervisor.service import TaskSupervisorService
from gg.server.task_supervisor.store import StartKeyConflictError


task_supervisor_router = APIRouter(prefix="/task-executions", tags=["TaskExecutions"])


@task_supervisor_router.post("/start")
async def start_task_execution(
    request: StartTaskExecutionRequest,
    response: Response,
    service: TaskSupervisorService = Depends(get_task_supervisor_service),
) -> TaskExecutionRecord:
    """Persist execution identity and launch work without blocking on completion."""

    try:
        record, created = await service.start(request)
    except StartKeyConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    response.status_code = (
        status.HTTP_202_ACCEPTED if created else status.HTTP_200_OK
    )
    return record


@task_supervisor_router.get("/{execution_id}")
async def get_task_execution(
    execution_id: str,
    service: TaskSupervisorService = Depends(get_task_supervisor_service),
) -> TaskExecutionRecord:
    try:
        return service.get_execution(execution_id)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@task_supervisor_router.get("/{execution_id}/manifest")
async def get_task_manifest(
    execution_id: str,
    service: TaskSupervisorService = Depends(get_task_supervisor_service),
) -> TaskResultManifest:
    try:
        return service.get_manifest(execution_id)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


__all__ = ["task_supervisor_router"]
