from __future__ import annotations

import ast
from pathlib import Path

from starlette.testclient import TestClient

from gg.sdk import ConversationStatus, EventKind
from gg.sdk.demo import local_server_notes
from gg.sdk.demo.local_server_notes import EVENTS_AFTER_RUN, run_demo
from gg.server import Settings, create_app


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        conversations_dir=tmp_path / "conversations",
        workspace_dir=tmp_path / "project",
    )


def test_demo_source_does_not_import_local_conversation() -> None:
    tree = ast.parse(
        Path(local_server_notes.__file__).read_text(encoding="utf-8"),
        filename=str(local_server_notes.__file__),
    )
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
            imported.update(f"{node.module}.{alias.name}" for alias in node.names)

    assert "gg.sdk.local_conversation" not in imported
    assert "LocalConversation" not in imported


def test_local_server_demo_reconnects_after_client_disconnect(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    message = "integration reconnect"
    with TestClient(app) as client:
        result = run_demo(
            client,
            websocket_connect=lambda conversation_id: client.websocket_connect(
                f"/sockets/events/{conversation_id}"
            ),
            message=message,
        )
        second_client = client.get(
            f"/api/conversations/{result.conversation_id}/events"
        )

    assert result.notes_path.is_file()
    assert result.notes_path.read_text(encoding="utf-8") == f"# Notes\n\n{message}\n"
    assert result.notes_path == tmp_path / "project" / "work" / "NOTES.md"

    assert len(result.events) == EVENTS_AFTER_RUN
    assert [event.seq for event in result.events] == [1, 2, 3, 4, 5]
    assert [event.kind for event in result.events] == [
        EventKind.MESSAGE,
        EventKind.STATUS,
        EventKind.ACTION,
        EventKind.OBSERVATION,
        EventKind.STATUS,
    ]
    assert result.events[-1].payload == {"status": ConversationStatus.FINISHED}

    assert result.live_events == result.reconnect_events
    assert result.reconnect_events == result.events
    assert second_client.status_code == 200
    assert second_client.json() == [
        event.model_dump(mode="json") for event in result.events
    ]
