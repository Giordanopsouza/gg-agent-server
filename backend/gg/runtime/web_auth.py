"""Shared browser session validation for the direct Google login."""

from __future__ import annotations

import sqlite3
from urllib.parse import urlsplit

from fastapi import HTTPException, Request

from gg.runtime.config import RuntimeSettings
from gg.runtime.local_sessions import LocalSessions, token_hash


SESSION_COOKIE = "gg_session"
FLOW_COOKIE = "gg_login_flow"


def _safe_return_path(value: str) -> str:
    parsed = urlsplit(value)
    if (
        not value.startswith("/")
        or value.startswith("//")
        or "\\" in value
        or any(ord(char) < 32 for char in value)
        or parsed.scheme
        or parsed.netloc
        or parsed.fragment
    ):
        raise HTTPException(status_code=400, detail="invalid return path")
    return value


def _require_origin(request: Request, settings: RuntimeSettings) -> None:
    if request.headers.get("origin") != settings.web_origin:
        raise HTTPException(status_code=403, detail="invalid origin")


async def authenticated_web_user(
    sessions: LocalSessions,
    cookie: str,
) -> dict[str, str]:
    try:
        user = await sessions.user(cookie)
        return {**user, "session_id": token_hash(cookie)}
    except sqlite3.Error:
        raise HTTPException(
            status_code=503, detail="session store unavailable"
        ) from None
