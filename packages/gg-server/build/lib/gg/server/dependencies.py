"""FastAPI dependencies shared across API routers."""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader

from gg.server.config import Settings
from gg.server.conversation_service import ConversationService


_SESSION_API_KEY_HEADER = APIKeyHeader(name="X-Session-API-Key", auto_error=False)


def check_session_api_key(
    request: Request,
    session_api_key: str | None = Depends(_SESSION_API_KEY_HEADER),
) -> None:
    """Reject the request when keys are configured and the header is missing or wrong.

    Reads ``session_api_keys`` from ``request.app.state.settings`` at request time
    so tests can build the app with different settings without re-registering routes.
    An empty key list leaves ``/api/*`` open (localhost bind is the other guard).
    """
    settings: Settings = request.app.state.settings
    if settings.session_api_keys and session_api_key not in settings.session_api_keys:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED)


def get_conversation_service(request: Request) -> ConversationService:
    """Return the process-wide manager created during app lifespan."""
    service = getattr(request.app.state, "conversation_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Conversation service is not available",
        )
    return service
