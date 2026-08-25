from pathlib import Path

from starlette.testclient import TestClient

from gg.sdk import Conversation, ConversationStatus, EventKind, RemoteWorkspace
from gg.server import Settings, create_app


def test_remote_client_writes_notes_through_real_app(tmp_path: Path) -> None:
    app = create_app(
        Settings(
            conversations_dir=tmp_path / "conversations",
            workspace_dir=tmp_path / "project",
            session_api_keys=["integration-secret"],
        )
    )
    workspace = RemoteWorkspace(
        host="http://testserver",
        working_dir="work",
        api_key="integration-secret",
    )

    with TestClient(app, headers=workspace.headers) as client:
        conversation = Conversation(workspace=workspace, client=client)
        message = conversation.send_message("remote integration")
        conversation.run()
        events = conversation.list_events()

    notes = tmp_path / "project" / "work" / "NOTES.md"
    assert notes.read_text(encoding="utf-8") == "# Notes\n\nremote integration\n"
    assert conversation.status == ConversationStatus.FINISHED
    assert message.kind == EventKind.MESSAGE
    assert [event.kind for event in events] == [
        EventKind.MESSAGE,
        EventKind.STATUS,
        EventKind.ACTION,
        EventKind.OBSERVATION,
        EventKind.STATUS,
    ]
