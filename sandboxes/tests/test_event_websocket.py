from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from gg.sdk import ConversationStatus, Event, EventKind
from gg.server import Settings, create_app
from gg.server.agent import local_conversation as local_conversation_module
from gg.server.agent.agent_backend import EventEmitter
from gg.server.agent.local_workspace import LocalWorkspace
from gg.server.websocket_routes import _serve_connection


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


def test_socket_receives_events_published_by_rest_run(
    tmp_path: Path, scripted_agent
) -> None:
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
    scripted_agent,
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
    assert snapshot["payload"] == {"role": "user", "text": "rest stays idle"}
    assert received[0]["payload"] == {"role": "user", "text": "socket runs"}
    assert received[-1]["payload"] == {"status": ConversationStatus.FINISHED}


def test_reconnect_replays_persisted_event_snapshot(
    tmp_path: Path, scripted_agent
) -> None:
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


def test_reconnect_cursor_only_replays_later_events(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        conversation_id = _start_conversation(client)
        for content in ("one", "two"):
            client.post(
                f"/api/conversations/{conversation_id}/events",
                json={"content": content},
            )

        with client.websocket_connect(
            f"/sockets/events/{conversation_id}?after_seq=1"
        ) as first:
            second = first.receive_json()

        client.post(
            f"/api/conversations/{conversation_id}/events",
            json={"content": "three"},
        )
        with client.websocket_connect(
            f"/sockets/events/{conversation_id}?after_seq={second['seq']}"
        ) as reconnected:
            third = reconnected.receive_json()

    assert second["seq"] == 2
    assert second["payload"]["text"] == "two"
    assert third["seq"] == 3
    assert third["payload"]["text"] == "three"


def test_subscribe_before_snapshot_closes_replay_live_race(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        conversation_id = _start_conversation(client)
        service = app.state.conversation_service
        original_list_events = service.list_events
        raced = False

        def list_events_with_race(requested_id: str) -> list[Event]:
            nonlocal raced
            if not raced:
                raced = True
                event = service.send_message(requested_id, "during snapshot")
                asyncio.get_running_loop().create_task(
                    service.event_stream(requested_id).publish(event)
                )
            return original_list_events(requested_id)

        service.list_events = list_events_with_race
        with client.websocket_connect(f"/sockets/events/{conversation_id}") as socket:
            snapshot_event = socket.receive_json()
            client.post(
                f"/api/conversations/{conversation_id}/events",
                json={"content": "after snapshot"},
            )
            live_event = socket.receive_json()

    assert snapshot_event["seq"] == 1
    assert snapshot_event["payload"]["text"] == "during snapshot"
    assert live_event["seq"] == 2
    assert live_event["payload"]["text"] == "after snapshot"


def test_socket_receives_agent_event_before_blocked_run_finishes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = threading.Event()
    release = threading.Event()

    class BlockingBackend:
        def run(
            self,
            prompt: str,
            workspace: LocalWorkspace,
            emit: EventEmitter,
        ) -> None:
            emit(EventKind.ACTION, {"tool": "blocked", "args": {}})
            started.set()
            assert release.wait(timeout=5)
            emit(EventKind.OBSERVATION, {"result": "released"})

        monkeypatch.setattr(
            local_conversation_module,
            "create_agent_backend",
            lambda config: BlockingBackend(),
        )

    app = create_app(_settings(tmp_path))
    try:
        with TestClient(app) as client:
            conversation_id = _start_conversation(client)
            with client.websocket_connect(
                f"/sockets/events/{conversation_id}"
            ) as socket:
                socket.send_json({"type": "message", "content": "block"})
                received = [socket.receive_json() for _ in range(3)]
                assert started.wait(timeout=1)
                health = client.get("/health")
                record = client.get(f"/api/conversations/{conversation_id}")
                assert record.json()["status"] == ConversationStatus.RUNNING
                release.set()
                received.extend(socket.receive_json() for _ in range(2))
    finally:
        release.set()

    assert health.status_code == 200
    assert [event["kind"] for event in received] == [
        EventKind.MESSAGE,
        EventKind.STATUS,
        EventKind.ACTION,
        EventKind.OBSERVATION,
        EventKind.STATUS,
    ]


def test_two_conversation_streams_are_isolated(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        first_id = _start_conversation(client)
        second_id = _start_conversation(client)
        with (
            client.websocket_connect(f"/sockets/events/{first_id}") as first,
            client.websocket_connect(f"/sockets/events/{second_id}") as second,
        ):
            client.post(
                f"/api/conversations/{first_id}/events",
                json={"content": "first only"},
            )
            client.post(
                f"/api/conversations/{second_id}/events",
                json={"content": "second only"},
            )
            first_event = first.receive_json()
            second_event = second.receive_json()

    assert first_event["payload"]["text"] == "first only"
    assert second_event["payload"]["text"] == "second only"


@pytest.mark.anyio
async def test_slow_subscriber_disconnect_includes_recovery_cursor() -> None:
    class FakeWebSocket:
        def __init__(self) -> None:
            self.closed: tuple[int, str] | None = None

        async def receive_json(self) -> Any:
            await asyncio.Event().wait()

        async def send_json(self, payload: Any) -> None:
            raise AssertionError(f"unexpected payload: {payload}")

        async def close(self, *, code: int, reason: str) -> None:
            self.closed = (code, reason)

    websocket = FakeWebSocket()
    overflowed = asyncio.Event()
    overflowed.set()

    await _serve_connection(
        websocket,  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        "conversation",
        asyncio.Queue(maxsize=1),
        overflowed,
        7,
    )

    assert websocket.closed == (1013, "resume_after=7")


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
