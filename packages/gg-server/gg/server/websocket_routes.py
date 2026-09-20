"""WebSocket event streaming for conversations."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from gg.sdk import ConversationNotFoundError, Event, SendMessageRequest
from gg.server.conversation_service import ConversationService
from gg.server.pubsub import SubscriberLimitExceededError


event_socket_router = APIRouter(prefix="/sockets/events", tags=["Events"])
_SUBSCRIBER_QUEUE_SIZE = 100


@event_socket_router.websocket("/{conversation_id}")
async def stream_events(
    websocket: WebSocket,
    conversation_id: str,
    after_seq: int = Query(default=0, ge=0),
) -> None:
    """Authenticate, replay persisted events, then stream new events.

    Keyed servers require the first incoming frame to carry the session key.
    Once connected, a ``{\"type\": \"message\", \"content\": ...}`` frame
    appends a message and starts the selected agent, unlike the REST default.
    """
    await websocket.accept()
    service = _conversation_service(websocket)
    if service is None:
        await websocket.close(code=status.WS_1013_TRY_AGAIN_LATER)
        return

    if not await _is_authenticated(websocket):
        await websocket.close(code=4001)
        return

    try:
        stream = service.event_stream(conversation_id)
    except ConversationNotFoundError:
        await websocket.close(code=4004)
        return

    pending_events: asyncio.Queue[Event] = asyncio.Queue(maxsize=_SUBSCRIBER_QUEUE_SIZE)
    overflowed = asyncio.Event()

    async def receive_event(event: Event) -> None:
        try:
            pending_events.put_nowait(event)
        except asyncio.QueueFull:
            overflowed.set()

    try:
        stream.subscribe(receive_event)
    except SubscriberLimitExceededError:
        await websocket.close(code=status.WS_1013_TRY_AGAIN_LATER)
        return

    try:
        # Subscribe before reading disk. Events persisted during the snapshot
        # appear in both places and are deduplicated below; none can fall into
        # the old replay/subscription gap.
        snapshot = service.list_events(conversation_id)
        last_sent = after_seq
        for event in snapshot:
            if event.seq <= last_sent:
                continue
            await websocket.send_json(event.model_dump(mode="json"))
            last_sent = event.seq
        await _serve_connection(
            websocket,
            service,
            conversation_id,
            pending_events,
            overflowed,
            last_sent,
        )
    except WebSocketDisconnect:
        pass
    finally:
        stream.unsubscribe(receive_event)


def _conversation_service(websocket: WebSocket) -> ConversationService | None:
    """Get the lifespan-owned service without treating a socket as an HTTP request."""
    service = getattr(websocket.app.state, "conversation_service", None)
    if isinstance(service, ConversationService):
        return service
    return None


async def _is_authenticated(websocket: WebSocket) -> bool:
    """Read the required first auth frame when the server has session keys."""
    settings = websocket.app.state.settings
    if not settings.session_api_keys:
        return True
    try:
        frame = await websocket.receive_json()
    except (WebSocketDisconnect, ValueError):
        return False
    return (
        isinstance(frame, dict)
        and frame.get("type") == "auth"
        and frame.get("session_api_key") in settings.session_api_keys
    )


async def _serve_connection(
    websocket: WebSocket,
    service: ConversationService,
    conversation_id: str,
    pending_events: asyncio.Queue[Event],
    overflowed: asyncio.Event,
    last_sent: int,
) -> None:
    """Forward live events while accepting chat frames from the same socket."""
    while True:
        incoming = asyncio.create_task(websocket.receive_json())
        next_event = asyncio.create_task(pending_events.get())
        overflow = asyncio.create_task(overflowed.wait())
        done, pending = await asyncio.wait(
            {incoming, next_event, overflow}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
        for task in pending:
            with suppress(asyncio.CancelledError):
                await task

        if overflow in done and overflow.result():
            await websocket.close(
                code=status.WS_1013_TRY_AGAIN_LATER,
                reason=f"resume_after={last_sent}",
            )
            return
        if next_event in done:
            event = next_event.result()
            if event.seq > last_sent:
                await websocket.send_json(event.model_dump(mode="json"))
                last_sent = event.seq
        if incoming in done:
            await _handle_message(service, conversation_id, incoming.result())


async def _handle_message(
    service: ConversationService, conversation_id: str, payload: Any
) -> None:
    """Validate a chat frame and deliberately run the agent after it is stored."""
    request = SendMessageRequest.model_validate(payload)
    await service.send_message_and_publish(conversation_id, request.content)
    task = asyncio.create_task(service.run(conversation_id))
    task.add_done_callback(_consume_run_result)


def _consume_run_result(task: asyncio.Task[object]) -> None:
    """Retrieve background run failures so the socket loop remains responsive."""
    with suppress(asyncio.CancelledError, Exception):
        task.result()
