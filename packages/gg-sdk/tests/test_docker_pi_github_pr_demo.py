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

from gg.sdk import ConversationStatus, RemoteWorkspace
from gg.sdk.demo import docker_pi_github_pr


OPENROUTER_SECRET = "openrouter-must-not-leak"
GITHUB_SECRET = "github-must-not-leak"
FAKE_EVENTS = [
    {
        "id": "event-1",
        "seq": 1,
        "kind": "message",
        "payload": {"role": "user", "text": "clone and edit"},
        "created_at": "2026-09-15T12:00:00Z",
    },
    {
        "id": "event-2",
        "seq": 2,
        "kind": "status",
        "payload": {"status": "running"},
        "created_at": "2026-09-15T12:00:01Z",
    },
    {
        "id": "event-3",
        "seq": 3,
        "kind": "action",
        "payload": {"tool": "write", "args": {"path": "index.html"}},
        "created_at": "2026-09-15T12:00:02Z",
    },
    {
        "id": "event-4",
        "seq": 4,
        "kind": "observation",
        "payload": {"tool": "write", "result": "file written", "is_error": False},
        "created_at": "2026-09-15T12:00:03Z",
    },
    {
        "id": "event-5",
        "seq": 5,
        "kind": "message",
        "payload": {"role": "assistant", "text": "Opened a pull request."},
        "created_at": "2026-09-15T12:00:04Z",
    },
    {
        "id": "event-6",
        "seq": 6,
        "kind": "status",
        "payload": {"status": "finished"},
        "created_at": "2026-09-15T12:00:05Z",
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
        index = len(self.instances)
        self.image = image
        self.secret_env_names = tuple(secret_env_names or ())
        self.volumes = tuple(volumes or ())
        self.timeout = timeout
        self.container_id = f"demo-container-{index}"
        self.conversation_id = f"docker-pi-github-pr-{index}"
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
            return httpx.Response(201, json=_record(self.conversation_id))
        if request.url.path.endswith("/events") and request.method == "POST":
            return httpx.Response(200, json=FAKE_EVENTS[0])
        if request.url.path.endswith("/run"):
            return httpx.Response(
                200,
                json=_record(self.conversation_id, status="finished"),
            )
        if request.url.path.endswith("/events") and request.method == "GET":
            return httpx.Response(200, json=FAKE_EVENTS)
        raise AssertionError(f"unexpected request: {request.method} {request.url}")


def _set_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", OPENROUTER_SECRET)
    monkeypatch.setenv("GH_TOKEN", GITHUB_SECRET)


def _list_pull_requests(container_id: str) -> str:
    slug = {
        "demo-container-0": "title",
        "demo-container-1": "background",
        "demo-container-2": "font",
    }[container_id]
    return json.dumps(
        [
            {
                "title": f"offline-marker-049-{slug}",
                "url": f"https://example.invalid/pr/{slug}",
            }
        ]
    )


def test_docker_pi_github_pr_demo_starts_three_sandboxes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_secrets(monkeypatch)
    FakeDockerWorkspace.instances.clear()

    results = docker_pi_github_pr.run_demo(
        image="gg-agent-server:test",
        marker="offline-marker-049",
        workspace_factory=FakeDockerWorkspace,
        pull_request_lister=_list_pull_requests,
    )

    workspaces = FakeDockerWorkspace.instances
    assert [task.slug for task in docker_pi_github_pr.WEBSITE_TASKS] == [
        "title",
        "background",
        "font",
    ]
    assert len(workspaces) == 3
    assert len(results) == 3
    assert [workspace.container_id for workspace in workspaces] == [
        "demo-container-0",
        "demo-container-1",
        "demo-container-2",
    ]
    assert all(workspace.stopped for workspace in workspaces)
    assert all(workspace.volumes == () for workspace in workspaces)
    assert all(
        workspace.secret_env_names == ("OPENROUTER_API_KEY", "GH_TOKEN")
        for workspace in workspaces
    )
    assert [result.slug for result in results] == ["title", "background", "font"]
    assert [result.marker for result in results] == [
        "offline-marker-049-title",
        "offline-marker-049-background",
        "offline-marker-049-font",
    ]
    assert all(result.repo == docker_pi_github_pr.DEFAULT_REPO for result in results)
    assert all(
        result.conversation_status == ConversationStatus.FINISHED for result in results
    )
    assert results[0].events_url == (
        "http://agent.example/api/conversations/docker-pi-github-pr-0/events"
    )

    prompts = [
        json.loads(workspace.requests[1].content)["content"] for workspace in workspaces
    ]
    assert "Change the website title" in prompts[0]
    assert "Change the page background color" in prompts[1]
    assert "Change the primary font family" in prompts[2]
    repo = docker_pi_github_pr.DEFAULT_REPO
    for prompt in prompts:
        assert f"gh repo clone {repo} ." in prompt
        assert "gh auth setup-git" in prompt
        assert OPENROUTER_SECRET not in prompt
        assert GITHUB_SECRET not in prompt


@pytest.mark.parametrize(
    ("missing", "pattern"),
    [
        ("OPENROUTER_API_KEY", "OPENROUTER_API_KEY must be set"),
        ("GH_TOKEN", "GH_TOKEN must be set"),
    ],
)
def test_docker_pi_github_pr_demo_requires_host_secrets(
    monkeypatch: pytest.MonkeyPatch,
    missing: str,
    pattern: str,
) -> None:
    _set_secrets(monkeypatch)
    monkeypatch.delenv(missing, raising=False)
    FakeDockerWorkspace.instances.clear()
    called = False

    def factory(**_: object) -> FakeDockerWorkspace:
        nonlocal called
        called = True
        raise AssertionError("workspace must not start without host secrets")

    with pytest.raises(RuntimeError, match=pattern):
        docker_pi_github_pr.run_demo(workspace_factory=factory)

    assert not called
    assert not FakeDockerWorkspace.instances


def test_docker_pi_github_pr_demo_rejects_invalid_repo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_secrets(monkeypatch)
    FakeDockerWorkspace.instances.clear()

    with pytest.raises(RuntimeError, match="repo must be OWNER/NAME"):
        docker_pi_github_pr.run_demo(
            repo="not-a-repo",
            workspace_factory=FakeDockerWorkspace,
        )

    assert not FakeDockerWorkspace.instances


def test_docker_pi_github_pr_demo_stops_all_containers_when_pr_check_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_secrets(monkeypatch)
    FakeDockerWorkspace.instances.clear()

    def missing_pr(container_id: str) -> str:
        return "[]"

    with pytest.raises(RuntimeError, match="open pull request list"):
        docker_pi_github_pr.run_demo(
            marker="offline-marker-049",
            workspace_factory=FakeDockerWorkspace,
            pull_request_lister=missing_pr,
        )

    assert len(FakeDockerWorkspace.instances) == 3
    assert all(workspace.stopped for workspace in FakeDockerWorkspace.instances)


def test_pause_keeps_containers_until_enter(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_secrets(monkeypatch)
    FakeDockerWorkspace.instances.clear()
    seen_running = False

    def fake_pause() -> None:
        nonlocal seen_running
        seen_running = True
        assert FakeDockerWorkspace.instances
        assert all(
            not workspace.stopped for workspace in FakeDockerWorkspace.instances
        )

    monkeypatch.setattr(docker_pi_github_pr, "_pause_until_enter", fake_pause)

    docker_pi_github_pr.run_demo(
        marker="offline-marker-049",
        workspace_factory=FakeDockerWorkspace,
        pull_request_lister=_list_pull_requests,
        pause=True,
    )

    assert seen_running
    assert all(workspace.stopped for workspace in FakeDockerWorkspace.instances)
    output = capsys.readouterr().out
    assert "curl -s http://agent.example/api/conversations/" in output
    assert "docker-pi-github-pr-0/events" in output
    assert '"kind"' not in output


def test_docker_pi_github_pr_demo_cli_prints_three_prs_without_secrets(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_secrets(monkeypatch)
    FakeDockerWorkspace.instances.clear()

    results = docker_pi_github_pr.run_demo(
        image="gg-agent-server:cli",
        marker="offline-marker-049",
        workspace_factory=FakeDockerWorkspace,
        pull_request_lister=_list_pull_requests,
    )

    def fake_run_demo(
        *, repo: str, image: str, pause: bool = False
    ) -> tuple[docker_pi_github_pr.DockerPiGitHubTaskResult, ...]:
        assert repo == docker_pi_github_pr.DEFAULT_REPO
        assert image == "gg-agent-server:cli"
        assert pause is True
        return results

    monkeypatch.setattr(docker_pi_github_pr, "run_demo", fake_run_demo)
    monkeypatch.setattr(
        "sys.argv",
        ["docker_pi_github_pr", "--image", "gg-agent-server:cli"],
    )

    docker_pi_github_pr.main()

    output = capsys.readouterr().out
    assert "title: demo-container-0 (finished)" in output
    assert "background: demo-container-1 (finished)" in output
    assert "font: demo-container-2 (finished)" in output
    assert "https://example.invalid/pr/title" in output
    assert "https://example.invalid/pr/background" in output
    assert "https://example.invalid/pr/font" in output
    assert "JSONL events" not in output
    assert OPENROUTER_SECRET not in output
    assert GITHUB_SECRET not in output


def test_github_pr_demo_source_has_no_local_conversation_or_host_mount() -> None:
    source = Path(docker_pi_github_pr.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(docker_pi_github_pr.__file__))
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
    assert "secret_env_names=list(SECRET_ENV_NAMES)" in source
    assert "ExitStack" in source
    assert OPENROUTER_SECRET not in source
    assert GITHUB_SECRET not in source


@pytest.mark.docker
@pytest.mark.pi
@pytest.mark.skipif(
    os.getenv("GG_RUN_DOCKER_PI_TESTS") != "1",
    reason="set GG_RUN_DOCKER_PI_TESTS=1 to run the paid Docker Pi smoke test",
)
def test_live_docker_pi_github_pr_demo() -> None:
    if shutil.which("docker") is None:
        pytest.skip("Docker CLI is not installed")
    inspect = subprocess.run(
        ["docker", "image", "inspect", docker_pi_github_pr.DEFAULT_IMAGE],
        capture_output=True,
        check=False,
    )
    if inspect.returncode != 0:
        pytest.skip(f"{docker_pi_github_pr.DEFAULT_IMAGE} image is not built")
    if not os.getenv("OPENROUTER_API_KEY"):
        pytest.skip("OPENROUTER_API_KEY is not configured")
    if not os.getenv("GH_TOKEN"):
        pytest.skip("GH_TOKEN is not configured")

    results = docker_pi_github_pr.run_demo()

    assert [result.slug for result in results] == ["title", "background", "font"]
    assert all(
        result.conversation_status == ConversationStatus.FINISHED for result in results
    )
    for result in results:
        assert result.marker in result.pull_requests
        leftover = subprocess.run(
            ["docker", "ps", "--quiet", "--filter", f"id={result.container_id}"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert leftover.stdout.strip() == ""
        evidence = result.pull_requests + json.dumps(
            [event.model_dump(mode="json") for event in result.events]
        )
        assert os.environ["OPENROUTER_API_KEY"] not in evidence
        assert os.environ["GH_TOKEN"] not in evidence
