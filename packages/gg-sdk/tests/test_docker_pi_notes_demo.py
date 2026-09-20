from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from gg.sdk import ConversationStatus, EventKind, RemoteWorkspace
from gg.sdk.demo import docker_pi_notes


SECRET = "openrouter-must-not-leak"
FAKE_EVENTS = [
    {
        "id": "event-1",
        "seq": 1,
        "kind": "message",
        "payload": {
            "role": "user",
            "text": (
                "Create the file /workspace/project/PI_NOTES.md. "
                "The file must contain this exact unique marker: offline-marker-032."
            ),
        },
        "created_at": "2026-09-08T12:00:00Z",
    },
    {
        "id": "event-2",
        "seq": 2,
        "kind": "status",
        "payload": {"status": "running"},
        "created_at": "2026-09-08T12:00:01Z",
    },
    {
        "id": "event-3",
        "seq": 3,
        "kind": "action",
        "payload": {"tool": "write", "args": {"path": "PI_NOTES.md"}},
        "created_at": "2026-09-08T12:00:02Z",
    },
    {
        "id": "event-4",
        "seq": 4,
        "kind": "observation",
        "payload": {"tool": "write", "result": "file written", "is_error": False},
        "created_at": "2026-09-08T12:00:03Z",
    },
    {
        "id": "event-5",
        "seq": 5,
        "kind": "message",
        "payload": {"role": "assistant", "text": "Created PI_NOTES.md."},
        "created_at": "2026-09-08T12:00:04Z",
    },
    {
        "id": "event-6",
        "seq": 6,
        "kind": "status",
        "payload": {"status": "finished"},
        "created_at": "2026-09-08T12:00:05Z",
    },
]


def _record(conversation_id: str, status: str = "idle") -> dict[str, Any]:
    return {
        "id": conversation_id,
        "status": status,
        "working_dir": "/workspace/project",
        "created_at": datetime.now(UTC).isoformat(),
    }


class FakeDockerWorkspace(RemoteWorkspace):
    """A Docker-shaped remote workspace with an in-memory agent server."""

    instances: list[FakeDockerWorkspace] = []

    def __init__(
        self,
        *,
        image: str,
        working_dir: str,
        secret_env_names: list[str] | tuple[str, ...] | None = None,
        volumes: list[str] | tuple[str, ...] | None = None,
        timeout: float = 30.0,
        **_: object,
    ) -> None:
        super().__init__(host="http://agent.example", working_dir=working_dir)
        self.image = image
        self.secret_env_names = tuple(secret_env_names or ())
        self.volumes = tuple(volumes or ())
        self.timeout = timeout
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
            return httpx.Response(201, json=_record("docker-pi-conversation"))
        if request.url.path.endswith("/events") and request.method == "POST":
            return httpx.Response(200, json=FAKE_EVENTS[0])
        if request.url.path.endswith("/run"):
            return httpx.Response(
                200,
                json=_record("docker-pi-conversation", status="finished"),
            )
        if request.url.path.endswith("/events") and request.method == "GET":
            return httpx.Response(200, json=FAKE_EVENTS)
        raise AssertionError(f"unexpected request: {request.method} {request.url}")


def test_docker_pi_demo_forwards_pi_agent_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", SECRET)
    FakeDockerWorkspace.instances.clear()
    reads: list[tuple[str, str]] = []

    def read_container_file(container_id: str, path: str) -> str:
        reads.append((container_id, path))
        return "Pi docker demo: offline-marker-032\n"

    result = docker_pi_notes.run_demo(
        image="gg-agent-server:test",
        marker="offline-marker-032",
        workspace_factory=FakeDockerWorkspace,
        container_file_reader=read_container_file,
    )

    workspace = FakeDockerWorkspace.instances[0]
    create_payload = json.loads(workspace.requests[0].content)
    message_payload = json.loads(workspace.requests[1].content)

    assert workspace.image == "gg-agent-server:test"
    assert workspace.working_dir == "/workspace/project"
    assert workspace.secret_env_names == ("OPENROUTER_API_KEY",)
    assert workspace.volumes == ()
    assert workspace.timeout == 600.0
    assert workspace.stopped
    assert result.container_id == "demo-container"
    assert result.conversation_id == "docker-pi-conversation"
    assert result.conversation_status == ConversationStatus.FINISHED
    assert result.notes_path == "/workspace/project/PI_NOTES.md"
    assert result.marker == "offline-marker-032"
    assert result.marker in result.notes_content
    assert reads == [("demo-container", "/workspace/project/PI_NOTES.md")]
    assert create_payload == {
        "working_dir": "/workspace/project",
        "agent": {
            "kind": "pi",
            "provider": "openrouter",
            "model": "google/gemini-3.7-flash",
            "timeout_seconds": 600.0,
            "command_ack_timeout_seconds": 5.0,
            "cancel_grace_seconds": 5.0,
        },
    }
    assert "/workspace/project/PI_NOTES.md" in message_payload["content"]
    assert "offline-marker-032" in message_payload["content"]
    assert {event.kind for event in result.events} >= {
        EventKind.MESSAGE,
        EventKind.ACTION,
        EventKind.OBSERVATION,
        EventKind.STATUS,
    }
    assert [request.url.path for request in workspace.requests] == [
        "/api/conversations",
        "/api/conversations/docker-pi-conversation/events",
        "/api/conversations/docker-pi-conversation/run",
        "/api/conversations/docker-pi-conversation/events",
    ]
    assert SECRET not in json.dumps(create_payload)
    assert SECRET not in json.dumps(message_payload)
    assert SECRET not in json.dumps(
        [event.model_dump(mode="json") for event in result.events]
    )


def test_docker_pi_demo_requires_host_openrouter_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    FakeDockerWorkspace.instances.clear()
    called = False

    def factory(**_: object) -> FakeDockerWorkspace:
        nonlocal called
        called = True
        raise AssertionError("workspace must not start without the host key")

    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY must be set"):
        docker_pi_notes.run_demo(workspace_factory=factory)

    assert not called
    assert not FakeDockerWorkspace.instances


def test_docker_pi_demo_stops_container_when_file_check_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", SECRET)
    FakeDockerWorkspace.instances.clear()

    def missing_file(container_id: str, path: str) -> str:
        raise RuntimeError(f"missing {path} in {container_id}")

    with pytest.raises(RuntimeError, match="missing /workspace/project/PI_NOTES.md"):
        docker_pi_notes.run_demo(
            marker="offline-marker-032",
            workspace_factory=FakeDockerWorkspace,
            container_file_reader=missing_file,
        )

    assert FakeDockerWorkspace.instances[0].stopped


def test_docker_pi_demo_cli_prints_file_and_event_summary_without_secret(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", SECRET)
    FakeDockerWorkspace.instances.clear()

    def read_container_file(container_id: str, path: str) -> str:
        return "Pi docker demo: cli-marker\n"

    result = docker_pi_notes.run_demo(
        image="gg-agent-server:cli",
        marker="cli-marker",
        workspace_factory=FakeDockerWorkspace,
        container_file_reader=read_container_file,
    )

    def fake_run_demo(*, image: str) -> docker_pi_notes.DockerPiDemoResult:
        assert image == "gg-agent-server:cli"
        return result

    monkeypatch.setattr(docker_pi_notes, "run_demo", fake_run_demo)
    monkeypatch.setattr(
        "sys.argv",
        ["docker_pi_notes", "--image", "gg-agent-server:cli"],
    )

    docker_pi_notes.main()

    output = capsys.readouterr().out
    assert "demo-container:/workspace/project/PI_NOTES.md" in output
    assert "Pi docker demo: cli-marker" in output
    assert "Conversation: docker-pi-conversation (finished)" in output
    assert "Persisted events (6):" in output
    assert "action=1" in output
    assert "message=2" in output
    assert "observation=1" in output
    assert "status=2" in output
    assert SECRET not in output


def test_docker_pi_demo_source_has_no_local_conversation_or_host_mount() -> None:
    source = Path(docker_pi_notes.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(docker_pi_notes.__file__))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
            imported.update(f"{node.module}.{alias.name}" for alias in node.names)

    assert "gg.sdk.local_conversation" not in imported
    assert "LocalConversation" not in imported
    assert "volumes=" not in source
    assert "secret_env_names=[OPENROUTER_SECRET_NAME]" in source
    assert SECRET not in source


@pytest.mark.docker
@pytest.mark.pi
@pytest.mark.skipif(
    os.getenv("GG_RUN_DOCKER_PI_TESTS") != "1",
    reason="set GG_RUN_DOCKER_PI_TESTS=1 to run the paid Docker Pi smoke test",
)
def test_live_docker_pi_demo() -> None:
    if shutil.which("docker") is None:
        pytest.skip("Docker CLI is not installed")
    inspect = subprocess.run(
        ["docker", "image", "inspect", docker_pi_notes.DEFAULT_IMAGE],
        capture_output=True,
        check=False,
    )
    if inspect.returncode != 0:
        pytest.skip(f"{docker_pi_notes.DEFAULT_IMAGE} image is not built")
    if not os.getenv("OPENROUTER_API_KEY"):
        pytest.skip("OPENROUTER_API_KEY is not configured")

    result = docker_pi_notes.run_demo()

    assert result.notes_path == "/workspace/project/PI_NOTES.md"
    assert result.marker in result.notes_content
    assert result.conversation_status == ConversationStatus.FINISHED
    assert {event.kind for event in result.events} >= {
        EventKind.MESSAGE,
        EventKind.ACTION,
        EventKind.OBSERVATION,
        EventKind.STATUS,
    }
    leftover = subprocess.run(
        ["docker", "ps", "--quiet", "--filter", f"id={result.container_id}"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert leftover.stdout.strip() == ""
    assert os.environ["OPENROUTER_API_KEY"] not in result.notes_content
    assert os.environ["OPENROUTER_API_KEY"] not in json.dumps(
        [event.model_dump(mode="json") for event in result.events]
    )
