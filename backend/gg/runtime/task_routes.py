"""HTTP routes for the durable background task API.

Thin routes over ``TaskService``. Routes accept an operator credential or a
validated browser session scoped to its owner. Submission returns ``201`` for
new tasks and ``200`` for identical idempotent replays.
"""

from __future__ import annotations

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
    status,
)

from gg.runtime.scheduler import DispatchStatus, TaskScheduler
from gg.runtime.task_auth import operator_only, socket_owner
from gg.runtime.task_service import (
    StoragePressureError,
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
    response: Response,
    service: TaskService = Depends(_get_service),
) -> TaskRecord:
    try:
        record, created = service.submit(body, owner_id=request.state.owner_id)
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
    except StoragePressureError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    if created:
        request.app.state.task_scheduler.wake()
        response.status_code = status.HTTP_201_CREATED
    return record


@router.get("", response_model=list[TaskRecord])
def list_tasks(
    request: Request,
    service: TaskService = Depends(_get_service),
) -> list[TaskRecord]:
    return service.list(owner_id=request.state.owner_id)


@router.get(
    "/dispatch/status",
    response_model=DispatchStatus,
    dependencies=[Depends(operator_only)],
)
def get_dispatch_status(
    scheduler: TaskScheduler = Depends(_get_scheduler),
) -> DispatchStatus:
    return scheduler.status()


@router.get("/{task_id}/events", response_model=list[TaskEventCopy])
def list_task_events(
    task_id: str,
    request: Request,
    after: int = Query(default=0, ge=0),
    service: TaskService = Depends(_get_service),
    supervision: TaskSupervisionManager = Depends(_get_supervision),
) -> list[TaskEventCopy]:
    if service.get(task_id, owner_id=request.state.owner_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return supervision.list_event_copies(task_id, after_cursor=after)


@router.post("/{task_id}/messages", response_model=MessageReceipt)
async def send_task_message(
    task_id: str,
    body: TaskMessageRequest,
    request: Request,
    service: TaskService = Depends(_get_service),
    supervision: TaskSupervisionManager = Depends(_get_supervision),
) -> MessageReceipt:
    if service.get(task_id, owner_id=request.state.owner_id) is None:
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
    request: Request,
    service: TaskService = Depends(_get_service),
    supervision: TaskSupervisionManager = Depends(_get_supervision),
) -> MessageReceipt:
    if service.get(task_id, owner_id=request.state.owner_id) is None:
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
        record = service.cancel(task_id, owner_id=request.state.owner_id)
    except TaskControlError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    request.app.state.task_scheduler.wake()
    return record


@router.get("/{task_id}/result", response_model=TaskResultRecord)
def get_task_result(
    task_id: str,
    request: Request,
    service: TaskService = Depends(_get_service),
) -> TaskResultRecord:
    try:
        return service.result(task_id, owner_id=request.state.owner_id)
    except TaskControlError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/{task_id}/retry", response_model=TaskRecord)
def retry_task(
    task_id: str,
    body: RetryTaskRequest,
    request: Request,
    response: Response,
    service: TaskService = Depends(_get_service),
) -> TaskRecord:
    try:
        record, created = service.retry(task_id, body, owner_id=request.state.owner_id)
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
        response.status_code = status.HTTP_201_CREATED
    return record


@router.get("/{task_id}", response_model=TaskRecord)
def get_task(
    task_id: str,
    request: Request,
    service: TaskService = Depends(_get_service),
) -> TaskRecord:
    record = service.get(task_id, owner_id=request.state.owner_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return record


@event_socket_router.websocket("/{task_id}")
async def stream_task_events(
    websocket: WebSocket,
    task_id: str,
    after: int = Query(default=0, ge=0),
) -> None:
    try:
        owner_id = await socket_owner(websocket)
    except HTTPException:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    supervision: TaskSupervisionManager | None = getattr(
        websocket.app.state, "task_supervision", None
    )
    service: TaskService | None = getattr(websocket.app.state, "task_service", None)
    if (
        supervision is None
        or service is None
        or service.get(task_id, owner_id=owner_id) is None
    ):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await websocket.accept()
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
