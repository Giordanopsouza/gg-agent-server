"""WebSocket event streaming for conversations."""
from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from gg.sdk import ConversationNotFoundError, Event, SendMessageRequest
from gg.server.conversation_service import ConversationService
from gg.server.pubsub import SubscriberLimitExceededError


event_socket_router = APIRouter(prefix="/sockets/events", tags=["Events"])


@event_socket_router.websocket("/{conversation_id}")
async def stream_events(websocket: WebSocket, conversation_id: str) -> None:
    """Authenticate, replay persisted events, then stream new events.

    Keyed servers require the first incoming frame to carry the session key.
    Once connected, a ``{\"type\": \"message\", \"content\": ...}`` frame
    appends a message and starts the dummy agent, unlike the REST default.
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
        snapshot = service.list_events(conversation_id)
        stream = service.event_stream(conversation_id)
    except ConversationNotFoundError:
        await websocket.close(code=4004)
        return

    pending_events: asyncio.Queue[Event] = asyncio.Queue()

    async def receive_event(event: Event) -> None:
        pending_events.put_nowait(event)

    try:
        stream.subscribe(receive_event)
    except SubscriberLimitExceededError:
        await websocket.close(code=status.WS_1013_TRY_AGAIN_LATER)
        return

    try:
        for event in snapshot:
            await websocket.send_json(event.model_dump(mode="json"))
        await _serve_connection(websocket, service, conversation_id, pending_events)
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
) -> None:
    """Forward live events while accepting chat frames from the same socket."""
    while True:
        incoming = asyncio.create_task(websocket.receive_json())
        next_event = asyncio.create_task(pending_events.get())
        done, pending = await asyncio.wait(
            {incoming, next_event}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
        for task in pending:
            with suppress(asyncio.CancelledError):
                await task

        if next_event in done:
            await websocket.send_json(next_event.result().model_dump(mode="json"))
        if incoming in done:
            await _handle_message(service, conversation_id, incoming.result())


async def _handle_message(
    service: ConversationService, conversation_id: str, payload: Any
) -> None:
    """Validate a chat frame and deliberately run the agent after it is stored."""
    request = SendMessageRequest.model_validate(payload)
    await service.send_message_and_publish(conversation_id, request.content)
    await service.run_and_publish(conversation_id)
