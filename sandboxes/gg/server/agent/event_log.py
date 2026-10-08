from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from gg.sdk.agent_backend import AgentConfig, PiAgentConfig
from gg.sdk.domain import (
    ConversationRecord,
    ConversationStatus,
    Event,
    MessageReceipt,
)
from gg.server.sqlite_state import SandboxState, conversation_database


class BaseState(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: ConversationStatus
    working_dir: str
    agent: AgentConfig = Field(default_factory=PiAgentConfig)


def _store(conversation_dir: Path | str) -> tuple[SandboxState, str]:
    path = Path(conversation_dir)
    path.mkdir(parents=True, exist_ok=True)
    return SandboxState(conversation_database(path)), path.name


def _save(conversation_dir: Path | str, column: str, payload: str) -> None:
    store, key = _store(conversation_dir)
    with store.write() as connection:
        connection.execute(
            f"INSERT INTO conversations(directory, {column}) VALUES (?, ?) "
            f"ON CONFLICT(directory) DO UPDATE SET {column} = excluded.{column}",
            (key, payload),
        )


def _load(conversation_dir: Path | str, column: str) -> str:
    store, key = _store(conversation_dir)
    with store.connection() as connection:
        row = connection.execute(
            f"SELECT {column} FROM conversations WHERE directory = ?", (key,)
        ).fetchone()
    if row is None or row[0] is None:
        raise FileNotFoundError(f"missing {column} for {key}")
    return row[0]


def save_meta(conversation_dir: Path | str, record: ConversationRecord) -> None:
    _save(conversation_dir, "meta_json", record.model_dump_json())


def load_meta(conversation_dir: Path | str) -> ConversationRecord:
    return ConversationRecord.model_validate_json(_load(conversation_dir, "meta_json"))


def save_base_state(
    conversation_dir: Path | str,
    *,
    status: ConversationStatus,
    working_dir: str,
    agent: AgentConfig | None = None,
) -> None:
    state = BaseState(
        status=status, working_dir=working_dir, agent=agent or PiAgentConfig()
    )
    _save(conversation_dir, "base_json", state.model_dump_json())


def load_base_state(conversation_dir: Path | str) -> BaseState:
    return BaseState.model_validate_json(_load(conversation_dir, "base_json"))


def save_conversation_state(
    conversation_dir: Path | str, record: ConversationRecord, state: BaseState
) -> None:
    """Keep catalog metadata and agent base state consistent on crash."""
    store, key = _store(conversation_dir)
    with store.write() as connection:
        connection.execute(
            """INSERT INTO conversations VALUES (?, ?, ?)
               ON CONFLICT(directory) DO UPDATE SET
               meta_json = excluded.meta_json, base_json = excluded.base_json""",
            (key, record.model_dump_json(), state.model_dump_json()),
        )


class EventLog:
    """Append-only SQLite events in sequence order."""

    def __init__(self, conversation_dir: Path | str) -> None:
        self.conversation_dir = Path(conversation_dir)
        self.store, self.key = _store(conversation_dir)
        with self.store.write() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO conversations(directory) VALUES (?)", (self.key,)
            )

    def append(self, event: Event) -> None:
        with self.store.write() as connection:
            connection.execute(
                "INSERT INTO events VALUES (?, ?, ?, ?)",
                (self.key, event.seq, event.id, event.model_dump_json()),
            )

    def next_seq(self) -> int:
        with self.store.connection() as connection:
            return connection.execute(
                "SELECT COALESCE(MAX(seq), 0) + 1 FROM events WHERE conversation = ?",
                (self.key,),
            ).fetchone()[0]

    def list(self) -> list[Event]:
        with self.store.connection() as connection:
            rows = connection.execute(
                "SELECT payload FROM events WHERE conversation = ? ORDER BY seq",
                (self.key,),
            ).fetchall()
        return [Event.model_validate_json(row[0]) for row in rows]


class MessageReceiptStore:
    """SQLite receipts keyed by the original message identity."""

    def __init__(self, conversation_dir: Path | str) -> None:
        self.store, self.key = _store(conversation_dir)
        with self.store.write() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO conversations(directory) VALUES (?)", (self.key,)
            )

    def load(self, message_id: str) -> MessageReceipt | None:
        with self.store.connection() as connection:
            row = connection.execute(
                """SELECT payload FROM message_receipts
                   WHERE conversation = ? AND message_id = ?""",
                (self.key, message_id),
            ).fetchone()
        return None if row is None else MessageReceipt.model_validate_json(row[0])

    def save(self, receipt: MessageReceipt) -> None:
        with self.store.write() as connection:
            connection.execute(
                """INSERT INTO message_receipts VALUES (?, ?, ?)
                   ON CONFLICT(conversation, message_id)
                   DO UPDATE SET payload = excluded.payload""",
                (self.key, receipt.id, receipt.model_dump_json()),
            )
