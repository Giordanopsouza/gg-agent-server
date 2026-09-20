"""HTTP routes for the durable background task API.

Thin routes over ``TaskService``. All routes require the runtime control-plane
``X-API-Key``. Submission returns ``201 Created`` for new tasks and ``200 OK``
for idempotent replays of identical input.
"""

from __future__ import annotations

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import JSONResponse

from gg.runtime.scheduler import DispatchStatus, TaskScheduler
from gg.runtime.task_service import (
    TaskConflictError,
    TaskControlError,
    TaskService,
    TaskValidationError,
)
from gg.runtime.task_supervision.manager import TaskSupervisionManager
from gg.sdk.domain import MessageReceipt
from gg.sdk.task_supervision import (
    RetryTaskRequest,
    TaskEventCopy,
    TaskMessageRequest,
    TaskResultRecord,
)
from gg.sdk.tasks import CreateTaskRequest, TaskRecord


router = APIRouter(prefix="/tasks", tags=["tasks"])
event_socket_router = APIRouter(prefix="/tasks/sockets/events", tags=["tasks"])


def _get_service(request: Request) -> TaskService:
    return request.app.state.task_service


def _get_scheduler(request: Request) -> TaskScheduler:
    return request.app.state.task_scheduler


def _get_supervision(request: Request) -> TaskSupervisionManager:
    return request.app.state.task_supervision


@router.post("", response_model=TaskRecord)
def submit_task(
    body: CreateTaskRequest,
    request: Request,
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
    if created:
        request.app.state.task_scheduler.wake()
        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content=record.model_dump(mode="json"),
        )
    return record


@router.get("", response_model=list[TaskRecord])
def list_tasks(
    service: TaskService = Depends(_get_service),
) -> list[TaskRecord]:
    return service.list()


@router.get("/dispatch/status", response_model=DispatchStatus)
def get_dispatch_status(
    scheduler: TaskScheduler = Depends(_get_scheduler),
) -> DispatchStatus:
    return scheduler.status()


@router.get("/{task_id}/events", response_model=list[TaskEventCopy])
def list_task_events(
    task_id: str,
    after: int = Query(default=0, ge=0),
    service: TaskService = Depends(_get_service),
    supervision: TaskSupervisionManager = Depends(_get_supervision),
) -> list[TaskEventCopy]:
    if service.get(task_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return supervision.list_event_copies(task_id, after_cursor=after)


@router.post("/{task_id}/messages", response_model=MessageReceipt)
async def send_task_message(
    task_id: str,
    body: TaskMessageRequest,
    service: TaskService = Depends(_get_service),
    supervision: TaskSupervisionManager = Depends(_get_supervision),
) -> MessageReceipt:
    if service.get(task_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    try:
        return await supervision.send_message(
            task_id, message_id=body.id, content=body.content
        )
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/{task_id}/messages/{message_id}", response_model=MessageReceipt)
def get_task_message_receipt(
    task_id: str,
    message_id: str,
    service: TaskService = Depends(_get_service),
    supervision: TaskSupervisionManager = Depends(_get_supervision),
) -> MessageReceipt:
    if service.get(task_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    receipt = supervision.get_message_receipt(task_id, message_id)
    if receipt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return receipt


@router.post("/{task_id}/cancel", response_model=TaskRecord)
def cancel_task(
    task_id: str,
    request: Request,
    service: TaskService = Depends(_get_service),
) -> TaskRecord:
    try:
        record = service.cancel(task_id)
    except TaskControlError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    request.app.state.task_scheduler.wake()
    return record


@router.get("/{task_id}/result", response_model=TaskResultRecord)
def get_task_result(
    task_id: str,
    service: TaskService = Depends(_get_service),
) -> TaskResultRecord:
    try:
        return service.result(task_id)
    except TaskControlError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/{task_id}/retry", response_model=TaskRecord)
def retry_task(
    task_id: str,
    body: RetryTaskRequest,
    request: Request,
    service: TaskService = Depends(_get_service),
) -> TaskRecord | JSONResponse:
    try:
        record, created = service.retry(task_id, body)
    except TaskConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except TaskControlError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except TaskValidationError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    if created:
        request.app.state.task_scheduler.wake()
        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content=record.model_dump(mode="json"),
        )
    return record


@router.get("/{task_id}", response_model=TaskRecord)
def get_task(
    task_id: str,
    service: TaskService = Depends(_get_service),
) -> TaskRecord:
    record = service.get(task_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return record


@event_socket_router.websocket("/{task_id}")
async def stream_task_events(
    websocket: WebSocket,
    task_id: str,
    after: int = Query(default=0, ge=0),
) -> None:
    await websocket.accept()
    supervision: TaskSupervisionManager | None = getattr(
        websocket.app.state, "task_supervision", None
    )
    service: TaskService | None = getattr(websocket.app.state, "task_service", None)
    if supervision is None or service is None or service.get(task_id) is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    for copy in supervision.list_event_copies(task_id, after_cursor=after):
        await websocket.send_json(copy.model_dump(mode="json"))
        after = copy.cursor
    queue = supervision.subscribe_events(task_id)
    try:
        while True:
            copy = await queue.get()
            if copy.cursor <= after:
                continue
            await websocket.send_json(copy.model_dump(mode="json"))
            after = copy.cursor
    except WebSocketDisconnect:
        pass
    finally:
        supervision.unsubscribe_events(task_id, queue)


__all__ = ["event_socket_router", "router"]
