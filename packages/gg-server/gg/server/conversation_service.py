"""Process-wide manager for live and on-disk conversations."""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from gg.sdk import (
    ConversationNotFoundError,
    ConversationRecord,
    LocalConversation,
    LocalWorkspace,
    load_meta,
)
from gg.sdk.event_log import META_FILE
from gg.server.config import Settings


class ConversationService:
    """Create, cache, and list ``LocalConversation`` objects for this process."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._conversations_dir = settings.conversations_dir
        self._conversations_dir.mkdir(parents=True, exist_ok=True)
        self._live: dict[str, LocalConversation] = {}

    def create(self, working_dir: Path | str) -> ConversationRecord:
        """Allocate an id, persist meta, and return the catalog record."""
        conversation_id = str(uuid4())
        conversation_dir = self._conversations_dir / conversation_id
        workspace = LocalWorkspace(working_dir=self._resolve_working_dir(working_dir))
        conversation = LocalConversation(
            conversation_dir=conversation_dir,
            workspace=workspace,
            conversation_id=conversation_id,
        )
        self._live[conversation_id] = conversation
        return load_meta(conversation_dir)

    def get(self, conversation_id: str) -> LocalConversation:
        """Return a live object, hydrating from disk on first access."""
        if conversation_id in self._live:
            return self._live[conversation_id]

        conversation_dir = self._conversations_dir / conversation_id
        if not (conversation_dir / META_FILE).is_file():
            raise ConversationNotFoundError(conversation_id)

        conversation = LocalConversation.open(conversation_dir=conversation_dir)
        self._live[conversation_id] = conversation
        return conversation

    def list(self) -> list[ConversationRecord]:
        """Return catalog records from ``conversations_dir/*/meta.json``."""
        if not self._conversations_dir.is_dir():
            return []

        records: list[ConversationRecord] = []
        for child in self._conversations_dir.iterdir():
            meta_path = child / META_FILE
            if meta_path.is_file():
                records.append(load_meta(child))
        records.sort(key=lambda record: record.created_at)
        return records

    def _resolve_working_dir(self, working_dir: Path | str) -> Path:
        path = Path(working_dir)
        if path.is_absolute():
            return path
        return self._settings.workspace_dir / path
