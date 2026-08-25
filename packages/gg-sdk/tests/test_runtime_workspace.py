from __future__ import annotations

import httpx

from gg.sdk import Conversation, RemoteConversation, RuntimeWorkspace


def test_context_provisions_remote_workspace_and_stops_session() -> None:
    control_requests: list[httpx.Request] = []

    def control_plane(request: httpx.Request) -> httpx.Response:
        control_requests.append(request)
        if request.url.path == "/start":
            return httpx.Response(
                201,
                json={
                    "id": "session-123",
                    "url": "http://sandbox.test:8000/",
                    "session_api_key": "sandbox-secret",
                },
            )
        if request.url.path == "/stop":
            return httpx.Response(
                200,
                json={
                    "id": "session-123",
                    "url": "http://sandbox.test:8000",
                    "status": "stopped",
                },
            )
        raise AssertionError(f"unexpected control request: {request.url}")

    workspace = RuntimeWorkspace(
        runtime_api_url="http://runtime.test/",
        runtime_api_key="control-secret",
    )
    workspace._runtime_client = httpx.Client(
        base_url=workspace.runtime_api_url,
        transport=httpx.MockTransport(control_plane),
    )

    with workspace as running:
        assert running is workspace
        assert running.host == "http://sandbox.test:8000"
        assert running.api_key == "sandbox-secret"
        assert running.session_id == "session-123"

    assert [request.url.path for request in control_requests] == ["/start", "/stop"]
    assert all(
        request.headers["X-API-Key"] == "control-secret" for request in control_requests
    )
    assert control_requests[1].read() == b'{"id":"session-123"}'
    assert workspace.session_id is None


def test_conversation_uses_remote_transport_after_start() -> None:
    def control_plane(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/start"
        return httpx.Response(
            201,
            json={
                "id": "session-456",
                "url": "http://sandbox.test:8000",
                "session_api_key": "sandbox-secret",
            },
        )

    sandbox_requests: list[httpx.Request] = []

    def sandbox_plane(request: httpx.Request) -> httpx.Response:
        sandbox_requests.append(request)
        return httpx.Response(
            201,
            json={
                "id": "conversation-1",
                "status": "idle",
                "working_dir": "project",
            },
        )

    workspace = RuntimeWorkspace(
        runtime_api_url="http://runtime.test",
        runtime_api_key="control-secret",
        working_dir="project",
        keep_alive=True,
    )
    workspace._runtime_client = httpx.Client(
        base_url=workspace.runtime_api_url,
        transport=httpx.MockTransport(control_plane),
    )

    with workspace:
        workspace._client = httpx.Client(
            base_url=workspace.host,
            transport=httpx.MockTransport(sandbox_plane),
        )
        conversation = Conversation(workspace=workspace)

    assert isinstance(conversation, RemoteConversation)
    assert sandbox_requests[0].url == "http://sandbox.test:8000/api/conversations"
    assert sandbox_requests[0].headers["X-Session-API-Key"] == "sandbox-secret"
    assert sandbox_requests[0].read() == b'{"working_dir":"project"}'
    assert workspace.session_id == "session-456"
