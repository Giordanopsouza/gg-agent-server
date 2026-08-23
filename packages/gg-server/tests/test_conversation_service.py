from __future__ import annotations

from pathlib import Path

import pytest

from gg.sdk import (
    ConversationNotFoundError,
    ConversationStatus,
    LocalConversation,
    LocalWorkspace,
    StartConversationRequest,
    load_meta,
)
from gg.server.config import Settings
from gg.server.conversation_service import ConversationService


def test_create_allocates_id_and_writes_meta(tmp_path: Path) -> None:
    settings = Settings(
        conversations_dir=tmp_path / "conversations",
        workspace_dir=tmp_path / "project",
    )
    service = ConversationService(settings)

    record = service.create("work")

    assert record.id
    assert record.status == ConversationStatus.IDLE
    assert record.working_dir == str(tmp_path / "project" / "work")
    meta = load_meta(settings.conversations_dir / record.id)
    assert meta.id == record.id


def test_get_returns_cached_conversation(tmp_path: Path) -> None:
    settings = Settings(
        conversations_dir=tmp_path / "conversations",
        workspace_dir=tmp_path / "project",
    )
    service = ConversationService(settings)
    record = service.create("work")

    first = service.get(record.id)
    second = service.get(record.id)

    assert first is second


def test_get_hydrates_from_disk(tmp_path: Path) -> None:
    settings = Settings(
        conversations_dir=tmp_path / "conversations",
        workspace_dir=tmp_path / "project",
    )
    creator = ConversationService(settings)
    record = creator.create("work")
    conversation = creator.get(record.id)
    conversation.send_message("hello")
    conversation.run()

    reloaded_service = ConversationService(settings)
    restored = reloaded_service.get(record.id)

    assert restored.status == ConversationStatus.FINISHED
    assert restored.id == record.id


def test_list_includes_conversations_from_previous_process(tmp_path: Path) -> None:
    settings = Settings(
        conversations_dir=tmp_path / "conversations",
        workspace_dir=tmp_path / "project",
    )
    first_process = ConversationService(settings)
    first = first_process.create("alpha")
    second = first_process.create("beta")

    second_process = ConversationService(settings)
    records = second_process.list()

    assert {record.id for record in records} == {first.id, second.id}


def test_start_reattaches_existing_id(tmp_path: Path) -> None:
    settings = Settings(
        conversations_dir=tmp_path / "conversations",
        workspace_dir=tmp_path / "project",
    )
    service = ConversationService(settings)
    created = service.start(StartConversationRequest(working_dir="work"))
    record, is_new = created
    reattached, reattach_is_new = service.start(
        StartConversationRequest(working_dir="other", id=record.id)
    )

    assert is_new is True
    assert reattach_is_new is False
    assert reattached.id == record.id
    assert reattached.working_dir == record.working_dir


def test_get_unknown_id_raises_domain_error(tmp_path: Path) -> None:
    service = ConversationService(
        Settings(
            conversations_dir=tmp_path / "conversations",
            workspace_dir=tmp_path / "project",
        )
    )

    with pytest.raises(ConversationNotFoundError, match="missing-id"):
        service.get("missing-id")


def test_send_message_does_not_run(tmp_path: Path) -> None:
    settings = Settings(
        conversations_dir=tmp_path / "conversations",
        workspace_dir=tmp_path / "project",
    )
    service = ConversationService(settings)
    record = service.create("work")

    event = service.send_message(record.id, "stay idle")

    assert event.kind.value == "message"
    assert event.payload == {"text": "stay idle"}
    assert service.get_record(record.id).status == ConversationStatus.IDLE
    assert service.list_events(record.id) == [event]


def test_local_conversation_open_preserves_status(tmp_path: Path) -> None:
    workspace = LocalWorkspace(working_dir=tmp_path / "work")
    conv_dir = tmp_path / "conv-1"
    conversation = LocalConversation(conversation_dir=conv_dir, workspace=workspace)
    conversation.send_message("persist")
    conversation.run()

    reopened = LocalConversation.open(conversation_dir=conv_dir)

    assert reopened.status == ConversationStatus.FINISHED
    assert reopened.id == conversation.id
