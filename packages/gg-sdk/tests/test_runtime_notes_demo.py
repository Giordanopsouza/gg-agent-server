from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from gg.sdk import EventKind, RemoteWorkspace
from gg.sdk.demo import runtime_notes


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


class FakeRuntimeWorkspace(RemoteWorkspace):
    """Runtime-shaped workspace with an in-memory sandbox HTTP plane."""

    instances: list[FakeRuntimeWorkspace] = []

    def __init__(
        self,
        *,
        runtime_api_url: str,
        runtime_api_key: str,
        working_dir: str,
    ) -> None:
        super().__init__(
            host="http://sandbox.example",
            working_dir=working_dir,
            api_key="sandbox-secret",
        )
        self.runtime_api_url = runtime_api_url
        self.runtime_api_key = runtime_api_key
        self.session_id: str | None = None
        self.stopped = False
        self.requests: list[httpx.Request] = []
        self._client = httpx.Client(
            base_url=self.host,
            transport=httpx.MockTransport(self._handle),
        )
        self.__class__.instances.append(self)

    def __enter__(self) -> FakeRuntimeWorkspace:
        self.session_id = "runtime-session"
        return self

    def __exit__(self, *_: object) -> None:
        self.stopped = True
        self.close()

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path == "/api/conversations":
            return httpx.Response(201, json=_record("runtime-conversation"))
        if request.url.path.endswith("/events") and request.method == "POST":
            return httpx.Response(
                200,
                json=_event(1, "message", {"text": "inside runtime"}),
            )
        if request.url.path.endswith("/run"):
            return httpx.Response(
                200,
                json=_record("runtime-conversation", status="finished"),
            )
        if request.url.path.endswith("/events") and request.method == "GET":
            return httpx.Response(
                200,
                json=[
                    _event(1, "message", {"text": "inside runtime"}),
                    _event(2, "status", {"status": "finished"}),
                ],
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")


def test_runtime_demo_proves_sandbox_file_and_cleanup() -> None:
    FakeRuntimeWorkspace.instances.clear()
    container_snapshots = iter(
        [
            {"pre-existing"},
            {"pre-existing", "runtime-sandbox"},
            {"pre-existing"},
        ]
    )
    reads: list[tuple[str, str]] = []

    def list_containers(image: str) -> set[str]:
        assert image == "gg-agent-server:test"
        return next(container_snapshots)

    def read_container_file(container_id: str, path: str) -> str:
        reads.append((container_id, path))
        return "# Notes\n\ninside runtime\n"

    result = runtime_notes.run_demo(
        runtime_api_url="http://runtime.example",
        runtime_api_key="control-secret",
        image="gg-agent-server:test",
        message="inside runtime",
        workspace_factory=FakeRuntimeWorkspace,
        container_lister=list_containers,
        container_file_reader=read_container_file,
    )

    workspace = FakeRuntimeWorkspace.instances[0]
    assert workspace.runtime_api_url == "http://runtime.example"
    assert workspace.runtime_api_key == "control-secret"
    assert workspace.stopped
    assert result.session_id == "runtime-session"
    assert result.container_id == "runtime-sandbox"
    assert result.conversation_id == "runtime-conversation"
    assert result.notes_path == "/workspace/project/NOTES.md"
    assert result.notes_content == "# Notes\n\ninside runtime\n"
    assert reads == [("runtime-sandbox", "/workspace/project/NOTES.md")]
    assert [event.kind for event in result.events] == [
        EventKind.MESSAGE,
        EventKind.STATUS,
    ]


def test_runtime_demo_uses_runtime_workspace_not_docker_workspace() -> None:
    tree = ast.parse(
        Path(runtime_notes.__file__).read_text(encoding="utf-8"),
        filename=str(runtime_notes.__file__),
    )
    imported_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_names.add(node.module)
            imported_names.update(f"{node.module}.{alias.name}" for alias in node.names)

    assert "gg.sdk.RuntimeWorkspace" in imported_names
    assert "DockerWorkspace" not in imported_names
    assert "gg.sdk.docker_workspace" not in imported_names
