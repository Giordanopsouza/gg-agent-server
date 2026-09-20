"""HTTP routes for the durable background task API.

Thin routes over ``TaskService``. All routes require the runtime control-plane
``X-API-Key``. Submission returns ``201 Created`` for new tasks and ``200 OK``
for idempotent replays of identical input.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

from gg.runtime.task_service import TaskConflictError, TaskService, TaskValidationError
from gg.sdk.tasks import CreateTaskRequest, TaskRecord


router = APIRouter(prefix="/tasks", tags=["tasks"])


# Pull the shared TaskService off the FastAPI app for route handlers.
def _get_service(request: Request) -> TaskService:
    return request.app.state.task_service


# POST /tasks — durably admit one background task.
@router.post("", response_model=TaskRecord)
def submit_task(
    body: CreateTaskRequest,
    service: TaskService = Depends(_get_service),
) -> TaskRecord | JSONResponse:
    try:
        record, created = service.submit(body)
    except TaskConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except TaskValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    # Idempotent replay of identical input returns the original task with 200.
    if created:
        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content=record.model_dump(mode="json"),
        )
    return record


# GET /tasks — list all tasks in FIFO order.
@router.get("", response_model=list[TaskRecord])
def list_tasks(
    service: TaskService = Depends(_get_service),
) -> list[TaskRecord]:
    return service.list()


# GET /tasks/{id} — fetch one task by id.
@router.get("/{task_id}", response_model=TaskRecord)
def get_task(
    task_id: str,
    service: TaskService = Depends(_get_service),
) -> TaskRecord:
    record = service.get(task_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return record


__all__ = ["router"]
