"""Separate operator credentials from validated browser task ownership."""

import secrets
from uuid import UUID

from fastapi import HTTPException, Request, Response, WebSocket, status

from gg.runtime.web_auth import SESSION_COOKIE, _require_origin, authenticated_web_user


async def bearer_owner(request: Request | WebSocket) -> UUID:
    settings = request.app.state.settings
    scheme, separator, token = request.headers.get("authorization", "").partition(" ")
    if (
        request.headers.get("x-api-key") is not None
        or scheme.lower() != "bearer"
        or not separator
        or not token.isascii()
        or not settings.wpp_api_token
        or not secrets.compare_digest(token, settings.wpp_api_token)
    ):
        raise HTTPException(status_code=401, detail="invalid WPP authorization")
    return settings.wpp_owner_id


async def task_access(request: Request, response: Response) -> None:
    if request.headers.get("authorization") is not None:
        if request.headers.get("x-api-key") is not None:
            raise HTTPException(status_code=401, detail="ambiguous authentication")
        request.state.owner_id = await bearer_owner(request)
        return
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
    user = await authenticated_web_user(request.app.state.web_sessions, cookie)
    request.state.owner_id = UUID(user["id"])


async def socket_owner(websocket: WebSocket) -> UUID | None:
    if websocket.headers.get("authorization") is not None:
        if websocket.headers.get("x-api-key") is not None:
            raise HTTPException(status_code=401, detail="ambiguous authentication")
        return await bearer_owner(websocket)
    settings = websocket.app.state.settings
    supplied_key = websocket.headers.get("x-api-key")
    if supplied_key is not None:
        if not secrets.compare_digest(supplied_key, settings.api_key):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
        return None
    cookie = websocket.cookies.get(SESSION_COOKIE, "")
    if not cookie or websocket.headers.get("origin") != settings.web_origin:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    user = await authenticated_web_user(websocket.app.state.web_sessions, cookie)
    return UUID(user["id"])


def operator_only(request: Request) -> None:
    if request.state.owner_id is not None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
