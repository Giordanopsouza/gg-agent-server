"""Separate operator credentials from validated browser task ownership."""

import secrets
from uuid import UUID

from fastapi import HTTPException, Request, Response, WebSocket, status

from gg.runtime.web_auth import SESSION_COOKIE, _require_origin, authenticated_web_user


async def task_access(request: Request, response: Response) -> None:
    settings = request.app.state.settings
    supplied_key = request.headers.get("x-api-key")
    if supplied_key is not None:
        if not secrets.compare_digest(supplied_key, settings.api_key):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
        request.state.owner_id = None
        return
    cookie = request.cookies.get(SESSION_COOKIE, "")
    if not cookie:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        _require_origin(request, settings)
    user = await authenticated_web_user(
        request.app.state.web_auth,
        request.app.state.web_sessions,
        cookie,
        response,
    )
    request.state.owner_id = UUID(user["id"])


async def socket_owner(websocket: WebSocket) -> UUID | None:
    settings = websocket.app.state.settings
    supplied_key = websocket.headers.get("x-api-key")
    if supplied_key is not None:
        if not secrets.compare_digest(supplied_key, settings.api_key):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
        return None
    cookie = websocket.cookies.get(SESSION_COOKIE, "")
    if not cookie or websocket.headers.get("origin") != settings.web_origin:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    user = await authenticated_web_user(
        websocket.app.state.web_auth, websocket.app.state.web_sessions, cookie
    )
    return UUID(user["id"])


def operator_only(request: Request) -> None:
    if request.state.owner_id is not None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
