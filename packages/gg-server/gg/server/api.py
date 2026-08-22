"""Placeholder /api router. Real conversation routes land in task 012."""
from __future__ import annotations

from fastapi import APIRouter


api_router = APIRouter(prefix="/api")


@api_router.get("/_auth_check")
async def auth_check() -> dict[str, str]:
    """Stub route so task 010 can prove auth wiring before conversation routes exist."""
    return {"status": "ok"}
