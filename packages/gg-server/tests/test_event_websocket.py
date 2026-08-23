from __future__ import annotations

from pathlib import Path

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from gg.sdk import ConversationStatus, EventKind
from gg.server import Settings, create_app


def _settings(tmp_path: Path, *, keys: list[str] | None = None) -> Settings:
    return Settings(
        conversations_dir=tmp_path / "conversations",
        workspace_dir=tmp_path / "project",
        session_api_keys=keys or [],
    )


def _start_conversation(client: TestClient) -> str:
    response = client.post("/api/conversations", json={"working_dir": "work"})
    assert response.status_code == 201
    return response.json()["id"]


def _event_count_after_run() -> int:
    return 4  # running status, write action, write observation, finished status


def test_socket_receives_events_published_by_rest_run(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        conversation_id = _start_conversation(client)
        with client.websocket_connect(f"/sockets/events/{conversation_id}") as socket:
            response = client.post(f"/api/conversations/{conversation_id}/run")
            received = [socket.receive_json() for _ in range(_event_count_after_run())]

    assert response.status_code == 200
    assert response.json()["status"] == ConversationStatus.FINISHED
    assert [event["kind"] for event in received] == [
        EventKind.STATUS,
        EventKind.ACTION,
        EventKind.OBSERVATION,
        EventKind.STATUS,
    ]
    assert [event["seq"] for event in received] == [1, 2, 3, 4]


def test_socket_message_runs_agent_while_rest_message_stays_idle(
    tmp_path: Path,
) -> None:
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        conversation_id = _start_conversation(client)
        rest_message = client.post(
            f"/api/conversations/{conversation_id}/events",
            json={"content": "rest stays idle"},
        )
        idle = client.get(f"/api/conversations/{conversation_id}")

        with client.websocket_connect(f"/sockets/events/{conversation_id}") as socket:
            snapshot = socket.receive_json()
            socket.send_json({"type": "message", "content": "socket runs"})
            received = [socket.receive_json() for _ in range(5)]

    assert rest_message.status_code == 200
    assert idle.json()["status"] == ConversationStatus.IDLE
    assert snapshot["payload"] == {"text": "rest stays idle"}
    assert received[0]["payload"] == {"text": "socket runs"}
    assert received[-1]["payload"] == {"status": ConversationStatus.FINISHED}
    assert (tmp_path / "project" / "work" / "NOTES.md").is_file()


def test_reconnect_replays_persisted_event_snapshot(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        conversation_id = _start_conversation(client)
        client.post(
            f"/api/conversations/{conversation_id}/events", json={"content": "replay"}
        )
        client.post(f"/api/conversations/{conversation_id}/run")
        with client.websocket_connect(f"/sockets/events/{conversation_id}") as first:
            first_snapshot = [first.receive_json() for _ in range(5)]
        with client.websocket_connect(f"/sockets/events/{conversation_id}") as second:
            second_snapshot = [second.receive_json() for _ in range(5)]

    assert [event["seq"] for event in first_snapshot] == [1, 2, 3, 4, 5]
    assert second_snapshot == first_snapshot


def test_keyed_socket_requires_first_auth_frame(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, keys=["secret"]))
    with TestClient(app, headers={"X-Session-API-Key": "secret"}) as client:
        conversation_id = _start_conversation(client)
        with pytest.raises(WebSocketDisconnect) as missing_auth:
            with client.websocket_connect(
                f"/sockets/events/{conversation_id}"
            ) as socket:
                socket.send_json({"type": "message", "content": "nope"})
                socket.receive_json()
        with pytest.raises(WebSocketDisconnect) as wrong_auth:
            with client.websocket_connect(
                f"/sockets/events/{conversation_id}"
            ) as socket:
                socket.send_json({"type": "auth", "session_api_key": "wrong"})
                socket.receive_json()
        with client.websocket_connect(f"/sockets/events/{conversation_id}") as socket:
            socket.send_json({"type": "auth", "session_api_key": "secret"})

    assert missing_auth.value.code == 4001
    assert wrong_auth.value.code == 4001


def test_socket_closes_unknown_conversation_with_4004(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as closed:
            with client.websocket_connect("/sockets/events/missing") as socket:
                socket.receive_json()

    assert closed.value.code == 4004
