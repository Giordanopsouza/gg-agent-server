from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from gg.sdk import ConversationStatus, EventKind, RemoteWorkspace
from gg.sdk.demo import docker_notes


def _record(conversation_id: str, status: str = "idle") -> dict[str, Any]:
    return {
        "id": conversation_id,
        "status": status,
        "working_dir": "/workspace/project",
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


class FakeDockerWorkspace(RemoteWorkspace):
    """A Docker-shaped remote workspace with an in-memory agent server."""

    instances: list[FakeDockerWorkspace] = []

    def __init__(self, *, image: str, working_dir: str) -> None:
        super().__init__(host="http://agent.example", working_dir=working_dir)
        self.image = image
        self.container_id = "demo-container"
        self.stopped = False
        self.requests: list[httpx.Request] = []
        self._client = httpx.Client(
            base_url=self.host,
            transport=httpx.MockTransport(self._handle),
        )
        self.instances.append(self)

    def __enter__(self) -> FakeDockerWorkspace:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
        self.stopped = True

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path == "/api/conversations":
            return httpx.Response(201, json=_record("docker-conversation"))
        if request.url.path.endswith("/events") and request.method == "POST":
            return httpx.Response(
                200,
                json=_event(1, "message", {"text": "inside Docker"}),
            )
        if request.url.path.endswith("/run"):
            return httpx.Response(
                200,
                json=_record("docker-conversation", status="finished"),
            )
        if request.url.path.endswith("/events") and request.method == "GET":
            return httpx.Response(
                200,
                json=[
                    _event(1, "message", {"text": "inside Docker"}),
                    _event(2, "status", {"status": "finished"}),
                ],
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")


def test_docker_demo_runs_through_remote_conversation_and_cleans_up() -> None:
    FakeDockerWorkspace.instances.clear()
    reads: list[tuple[str, str]] = []

    def read_container_file(container_id: str, path: str) -> str:
        reads.append((container_id, path))
        return "# Notes\n\ninside Docker\n"

    result = docker_notes.run_demo(
        image="gg-agent-server:test",
        message="inside Docker",
        workspace_factory=FakeDockerWorkspace,
        container_file_reader=read_container_file,
    )

    workspace = FakeDockerWorkspace.instances[0]
    assert workspace.image == "gg-agent-server:test"
    assert workspace.stopped
    assert result.container_id == "demo-container"
    assert result.conversation_id == "docker-conversation"
    assert result.notes_path == "/workspace/project/NOTES.md"
    assert result.notes_content == "# Notes\n\ninside Docker\n"
    assert reads == [("demo-container", "/workspace/project/NOTES.md")]
    assert [event.kind for event in result.events] == [
        EventKind.MESSAGE,
        EventKind.STATUS,
    ]
    assert result.events[-1].payload == {"status": ConversationStatus.FINISHED}
    assert [request.url.path for request in workspace.requests] == [
        "/api/conversations",
        "/api/conversations/docker-conversation/events",
        "/api/conversations/docker-conversation/run",
        "/api/conversations/docker-conversation/events",
    ]


def test_docker_demo_source_has_no_local_conversation_dependency() -> None:
    tree = ast.parse(
        Path(docker_notes.__file__).read_text(encoding="utf-8"),
        filename=str(docker_notes.__file__),
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
