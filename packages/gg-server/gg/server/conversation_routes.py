"""REST routes for conversation create, get, list, and run."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status

from gg.sdk import (
    ConversationAlreadyRunningError,
    ConversationNotFoundError,
    ConversationRecord,
    InvalidConversationStateError,
    StartConversationRequest,
)
from gg.server.conversation_service import ConversationService
from gg.server.dependencies import get_conversation_service


conversation_router = APIRouter(prefix="/conversations", tags=["Conversations"])


@conversation_router.post("")
async def start_conversation(
    request: StartConversationRequest,
    response: Response,
    service: ConversationService = Depends(get_conversation_service),
) -> ConversationRecord:
    """Create a conversation, or reattach when the same id is posted again."""
    record, is_new = service.start(request)
    response.status_code = (
        status.HTTP_201_CREATED if is_new else status.HTTP_200_OK
    )
    return record


@conversation_router.get("")
async def list_conversations(
    service: ConversationService = Depends(get_conversation_service),
) -> list[ConversationRecord]:
    """Return catalog records from on-disk meta files."""
    return service.list()


@conversation_router.get("/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    service: ConversationService = Depends(get_conversation_service),
) -> ConversationRecord:
    """Return one catalog record, or 404 when the id is unknown."""
    try:
        return service.get_record(conversation_id)
    except ConversationNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@conversation_router.post("/{conversation_id}/run")
async def run_conversation(
    conversation_id: str,
    service: ConversationService = Depends(get_conversation_service),
) -> ConversationRecord:
    """Run the dummy agent and return when the loop has finished."""
    try:
        return await service.run(conversation_id)
    except ConversationNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ConversationAlreadyRunningError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except InvalidConversationStateError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
