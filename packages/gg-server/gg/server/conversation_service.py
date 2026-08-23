"""Process-wide manager for live and on-disk conversations."""
from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4

from gg.sdk import (
    ConversationAlreadyRunningError,
    ConversationNotFoundError,
    ConversationRecord,
    Event,
    LocalConversation,
    LocalWorkspace,
    StartConversationRequest,
    load_meta,
)
from gg.sdk.event_log import META_FILE
from gg.server.config import Settings
from gg.server.pubsub import PubSub


class ConversationService:
    """Create, cache, and list ``LocalConversation`` objects for this process."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._conversations_dir = settings.conversations_dir
        self._conversations_dir.mkdir(parents=True, exist_ok=True)
        self._live: dict[str, LocalConversation] = {}
        self._run_lock = asyncio.Lock()
        self._run_tasks: dict[str, asyncio.Task[None]] = {}
        self._event_streams: dict[str, PubSub[Event]] = {}

    def create(
        self,
        working_dir: Path | str,
        conversation_id: str | None = None,
    ) -> ConversationRecord:
        """Allocate an id, persist meta, and return the catalog record."""
        conversation_id = conversation_id or str(uuid4())
        conversation_dir = self._conversations_dir / conversation_id
        workspace = LocalWorkspace(working_dir=self._resolve_working_dir(working_dir))
        conversation = LocalConversation(
            conversation_dir=conversation_dir,
            workspace=workspace,
            conversation_id=conversation_id,
        )
        self._live[conversation_id] = conversation
        return load_meta(conversation_dir)

    def start(
        self, request: StartConversationRequest
    ) -> tuple[ConversationRecord, bool]:
        """Create a conversation, or reattach when the id already exists."""
        if request.id is not None and self._exists(request.id):
            return self.get_record(request.id), False
        return self.create(request.working_dir, conversation_id=request.id), True

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

    def get_record(self, conversation_id: str) -> ConversationRecord:
        """Return the catalog record, hydrating the live object if needed."""
        conversation = self.get(conversation_id)
        return load_meta(conversation.conversation_dir)

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

    def send_message(self, conversation_id: str, content: str) -> Event:
        """Append a user message. Does not start the agent loop."""
        return self.get(conversation_id).send_message(content)

    def list_events(self, conversation_id: str) -> list[Event]:
        """Return persisted events in seq order."""
        return self.get(conversation_id).list_events()

    def event_stream(self, conversation_id: str) -> PubSub[Event]:
        """Return the live event stream for an existing conversation."""
        self.get(conversation_id)
        return self._event_streams.setdefault(conversation_id, PubSub())

    async def send_message_and_publish(
        self, conversation_id: str, content: str
    ) -> Event:
        """Append a message and fan it out to current live subscribers."""
        event = self.send_message(conversation_id, content)
        await self.event_stream(conversation_id).publish(event)
        return event

    async def run(self, conversation_id: str) -> ConversationRecord:
        """Run the dummy loop and wait until it finishes.

        A second call while a run task is still in flight raises
        ``ConversationAlreadyRunningError``.
        """
        conversation = self.get(conversation_id)
        async with self._run_lock:
            existing = self._run_tasks.get(conversation_id)
            if existing is not None and not existing.done():
                raise ConversationAlreadyRunningError()
            task = asyncio.create_task(asyncio.to_thread(conversation.run))
            self._run_tasks[conversation_id] = task
        await task
        return load_meta(conversation.conversation_dir)

    async def run_and_publish(self, conversation_id: str) -> ConversationRecord:
        """Run the dummy loop and fan out the events it appended.

        ``LocalConversation`` deliberately owns only persistence. The server
        compares the persisted log before and after a run so its transport
        layer can stream the new events without adding a server dependency to
        the SDK package.
        """
        existing_event_ids = {
            event.id for event in self.list_events(conversation_id)
        }
        record = await self.run(conversation_id)
        for event in self.list_events(conversation_id):
            if event.id not in existing_event_ids:
                await self.event_stream(conversation_id).publish(event)
        return record

    def _exists(self, conversation_id: str) -> bool:
        if conversation_id in self._live:
            return True
        return (self._conversations_dir / conversation_id / META_FILE).is_file()

    def _resolve_working_dir(self, working_dir: Path | str) -> Path:
        path = Path(working_dir)
        if path.is_absolute():
            return path
        return self._settings.workspace_dir / path
