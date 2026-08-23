"""Mounted /api router. Auth from task 010 applies to every route here."""
from __future__ import annotations

from fastapi import APIRouter

from gg.server.conversation_routes import conversation_router


api_router = APIRouter(prefix="/api")
api_router.include_router(conversation_router)
