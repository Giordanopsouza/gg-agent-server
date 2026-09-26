"""REST routes for conversation create, get, list, and run."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status

from gg.sdk import (
    ConversationRecord,
    MessageReceipt,
    StartConversationRequest,
    SteerMessageRequest,
)
from gg.server.agent import (
    AgentControlError,
    AgentError,
    ConversationAlreadyRunningError,
    ConversationNotFoundError,
    InvalidConversationStateError,
    MessageIdConflictError,
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
    response.status_code = status.HTTP_201_CREATED if is_new else status.HTTP_200_OK
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
    """Run the selected agent and return when the loop has finished."""
    try:
        return await service.run(conversation_id)
    except ConversationNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ConversationAlreadyRunningError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except InvalidConversationStateError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except AgentError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@conversation_router.post("/{conversation_id}/messages")
async def steer_conversation(
    conversation_id: str,
    request: SteerMessageRequest,
    service: ConversationService = Depends(get_conversation_service),
) -> MessageReceipt:
    """Durably accept one running-agent message and report Pi delivery knowledge.

    ``delivered_to_pi`` means Pi acknowledged queueing at its safe steering
    boundary, not that the model observed or acted on the message. ``unknown``
    is never automatically replayed because Pi may already have accepted it.
    """
    try:
        return await service.steer(conversation_id, request.id, request.content)
    except ConversationNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except MessageIdConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (InvalidConversationStateError, AgentControlError) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@conversation_router.get("/{conversation_id}/messages/{message_id}")
async def get_message_receipt(
    conversation_id: str,
    message_id: str,
    service: ConversationService = Depends(get_conversation_service),
) -> MessageReceipt:
    """Return the durable receipt for a previously accepted message."""
    try:
        receipt = service.get_message_receipt(conversation_id, message_id)
    except ConversationNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if receipt is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="message receipt not found",
        )
    return receipt


@conversation_router.post("/{conversation_id}/cancel")
async def cancel_conversation(
    conversation_id: str,
    service: ConversationService = Depends(get_conversation_service),
) -> ConversationRecord:
    """Abort the active Pi run and return only after process-tree termination."""
    try:
        return await service.cancel(conversation_id)
    except ConversationNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (InvalidConversationStateError, AgentControlError) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
