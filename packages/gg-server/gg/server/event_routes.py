"""REST routes for sending messages and listing conversation events."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from gg.sdk import (
    ConversationAlreadyRunningError,
    ConversationNotFoundError,
    Event,
    InvalidConversationStateError,
    SendMessageRequest,
)
from gg.server.conversation_service import ConversationService
from gg.server.dependencies import get_conversation_service


event_router = APIRouter(
    prefix="/conversations/{conversation_id}/events",
    tags=["Events"],
)


@event_router.post("")
async def send_message(
    conversation_id: str,
    request: SendMessageRequest,
    service: ConversationService = Depends(get_conversation_service),
) -> Event:
    """Append a user message. Does not start the loop unless ``run`` is true."""
    try:
        event = service.send_message(conversation_id, request.content)
        if request.run:
            await service.run(conversation_id)
        return event
    except ConversationNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ConversationAlreadyRunningError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except InvalidConversationStateError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@event_router.get("")
async def list_events(
    conversation_id: str,
    service: ConversationService = Depends(get_conversation_service),
) -> list[Event]:
    """Return persisted events in seq order."""
    try:
        return service.list_events(conversation_id)
    except ConversationNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
