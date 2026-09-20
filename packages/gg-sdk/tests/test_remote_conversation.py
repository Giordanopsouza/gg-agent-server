from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from gg.sdk import (
    Conversation,
    ConversationStatus,
    EventKind,
    LocalConversation,
    LocalWorkspace,
    MessageDeliveryStatus,
    PiAgentConfig,
    RemoteConversation,
    RemoteWorkspace,
    remote_conversation as remote_module,
)


def _record(conversation_id: str, status: str = "idle") -> dict[str, Any]:
    return {
        "id": conversation_id,
        "status": status,
        "working_dir": "/workspace/project/work",
        "created_at": datetime.now(UTC).isoformat(),
    }


def _event(seq: int, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"event-{seq}",
        "seq": seq,
        "kind": kind,
        "payload": payload,
        "created_at": "2026-08-25T12:00:00Z",
    }


def test_factory_selects_local_conversation(tmp_path: Path) -> None:
    workspace = LocalWorkspace(working_dir=tmp_path / "work")

    conversation = Conversation(
        workspace=workspace,
        conversation_dir=tmp_path / "conversation",
    )

    assert isinstance(conversation, LocalConversation)


def test_factory_forwards_pi_configuration_to_local_conversation(
    tmp_path: Path,
) -> None:
    agent = PiAgentConfig(model="test/model", timeout_seconds=29)

    conversation = Conversation(
        workspace=LocalWorkspace(working_dir=tmp_path / "work"),
        conversation_dir=tmp_path / "conversation",
        agent=agent,
    )

    assert isinstance(conversation, LocalConversation)
    assert conversation._agent == agent


def test_remote_conversation_uses_transport_contract() -> None:
    requests: list[httpx.Request] = []
    conversation_id = "conversation-1"

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/conversations":
            return httpx.Response(201, json=_record(conversation_id))
        if request.url.path.endswith("/events") and request.method == "POST":
            return httpx.Response(
                200,
                json=_event(1, "message", {"text": "hello"}),
            )
        if request.url.path.endswith("/run"):
            return httpx.Response(
                200,
                json=_record(conversation_id, status="finished"),
            )
        if request.url.path.endswith("/events") and request.method == "GET":
            return httpx.Response(
                200,
                json=[_event(1, "message", {"text": "hello"})],
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    workspace = RemoteWorkspace(
        host="http://agent.example/",
        working_dir="work",
        api_key="secret",
    )
    with httpx.Client(
        base_url=workspace.host,
        headers=workspace.headers,
        transport=httpx.MockTransport(handle),
    ) as client:
        conversation = Conversation(workspace=workspace, client=client)
        message = conversation.send_message("hello")
        conversation.run()
        events = conversation.list_events()

    assert isinstance(conversation, RemoteConversation)
    assert conversation.id == conversation_id
    assert conversation.status == ConversationStatus.FINISHED
    assert message.kind == EventKind.MESSAGE
    assert events == [message]

    create_payload = requests[0].read().decode()
    message_payload = requests[1].read().decode()
    assert create_payload == '{"working_dir":"work"}'
    assert "host" not in create_payload
    assert message_payload == '{"content":"hello","run":false}'
    assert all(request.headers["X-Session-API-Key"] == "secret" for request in requests)


def test_remote_conversation_reattaches_with_requested_id() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.read().decode() == (
            '{"working_dir":"/workspace/project","id":"known-id"}'
        )
        return httpx.Response(200, json=_record("known-id"))

    workspace = RemoteWorkspace(host="http://agent.example")
    with httpx.Client(
        base_url=workspace.host,
        transport=httpx.MockTransport(handle),
    ) as client:
        conversation = RemoteConversation(
            workspace=workspace,
            conversation_id="known-id",
            client=client,
        )

    assert conversation.id == "known-id"


def test_remote_conversation_forwards_pi_agent_configuration() -> None:
    agent = PiAgentConfig(model="test/model", timeout_seconds=17)

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.read().decode() == (
            '{"working_dir":"/workspace/project","agent":'
            '{"kind":"pi","provider":"openrouter","model":"test/model",'
            '"timeout_seconds":17.0,"command_ack_timeout_seconds":5.0,'
            '"cancel_grace_seconds":5.0}}'
        )
        return httpx.Response(201, json=_record("pi-id"))

    workspace = RemoteWorkspace(host="http://agent.example")
    with httpx.Client(
        base_url=workspace.host,
        transport=httpx.MockTransport(handle),
    ) as client:
        conversation = Conversation(workspace=workspace, agent=agent, client=client)

    assert conversation.id == "pi-id"


def test_remote_conversation_controls_active_run() -> None:
    conversation_id = "controlled"
    receipt = {
        "id": "message-1",
        "content": "steer",
        "status": "delivered_to_pi",
        "detail": None,
        "created_at": "2026-09-20T12:00:00Z",
        "updated_at": "2026-09-20T12:00:01Z",
    }

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/conversations":
            return httpx.Response(201, json=_record(conversation_id))
        if request.url.path.endswith("/messages"):
            assert request.read().decode() == ('{"id":"message-1","content":"steer"}')
            return httpx.Response(200, json=receipt)
        if request.url.path.endswith("/messages/message-1"):
            return httpx.Response(200, json=receipt)
        if request.url.path.endswith("/cancel"):
            return httpx.Response(
                200,
                json=_record(conversation_id, status="cancelled"),
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    workspace = RemoteWorkspace(host="http://agent.example")
    with httpx.Client(
        base_url=workspace.host,
        transport=httpx.MockTransport(handle),
    ) as client:
        conversation = RemoteConversation(workspace=workspace, client=client)
        delivered = conversation.steer("message-1", "steer")
        loaded = conversation.get_message_receipt("message-1")
        conversation.cancel()

    assert delivered == loaded
    assert delivered.status == MessageDeliveryStatus.DELIVERED
    assert conversation.status == ConversationStatus.CANCELLED


def test_subscription_uses_websocket_url_and_authenticates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = _event(5, "message", {"text": "from socket"})

    class FakeConnection:
        def __init__(self) -> None:
            self.sent: list[str] = []
            self.closed = False

        def send(self, payload: str) -> None:
            self.sent.append(payload)

        def recv(self, *, timeout: float | None = None) -> str:
            assert timeout == 2.0
            return httpx.Response(200, json=event).text

        def close(self) -> None:
            self.closed = True

    connection = FakeConnection()
    connected_urls: list[str] = []

    def fake_connect(url: str, **_: Any) -> FakeConnection:
        connected_urls.append(url)
        return connection

    monkeypatch.setattr(remote_module, "connect", fake_connect)
    workspace = RemoteWorkspace(
        host="https://agent.example/base/",
        api_key="socket-secret",
    )
    conversation = object.__new__(RemoteConversation)
    conversation.workspace = workspace
    conversation._record = remote_module.ConversationRecord.model_validate(
        _record("socket-conversation")
    )

    with conversation.subscribe(after_seq=4) as subscription:
        received = subscription.receive(timeout=2.0)

    assert connected_urls == [
        "wss://agent.example/base/sockets/events/socket-conversation?after_seq=4"
    ]
    assert connection.sent == ['{"type": "auth", "session_api_key": "socket-secret"}']
    assert connection.closed
    assert received.payload == {"text": "from socket"}
    assert subscription.cursor == 5
