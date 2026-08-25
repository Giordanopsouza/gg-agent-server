from __future__ import annotations

import subprocess
from collections.abc import Sequence
from typing import Any

import httpx
import pytest

from gg.sdk import (
    DockerWorkspace,
    DockerWorkspaceError,
    docker_workspace as docker_module,
)


def _completed(
    arguments: Sequence[str],
    *,
    stdout: str = "",
    stderr: str = "",
    returncode: int = 0,
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        ["docker", *arguments],
        returncode,
        stdout,
        stderr,
    )


def test_context_starts_healthy_authenticated_container_and_stops_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []
    health_requests: list[httpx.Request] = []

    def fake_docker(
        arguments: Sequence[str],
        *,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        command = list(arguments)
        commands.append(command)
        if command[0] == "run":
            return _completed(command, stdout="container-123\n")
        if command[0] == "port":
            return _completed(command, stdout="127.0.0.1:49152\n")
        if command[0] == "stop":
            assert not check
            return _completed(command, stdout="container-123\n")
        raise AssertionError(f"unexpected Docker command: {command}")

    def handle_health(request: httpx.Request) -> httpx.Response:
        health_requests.append(request)
        return httpx.Response(200, json={"status": "ok"})

    monkeypatch.setattr(DockerWorkspace, "_docker", staticmethod(fake_docker))
    workspace = DockerWorkspace(
        image="gg-agent-server:dev",
        api_key="launcher-secret",
    )
    workspace._client = httpx.Client(
        base_url="http://127.0.0.1:49152",
        headers=workspace.headers,
        transport=httpx.MockTransport(handle_health),
    )

    with workspace as running:
        assert running is workspace
        assert running.host == "http://127.0.0.1:49152"
        assert running.container_id == "container-123"

    run_command = commands[0]
    assert run_command == [
        "run",
        "--detach",
        "--rm",
        "--publish",
        "127.0.0.1::8000",
        "--env",
        "GG_SESSION_API_KEYS=launcher-secret",
        "gg-agent-server:dev",
    ]
    assert "--volume" not in run_command
    assert commands[-1] == ["stop", "container-123"]
    assert workspace.container_id is None
    assert health_requests[0].headers["X-Session-API-Key"] == "launcher-secret"


def test_explicit_volumes_are_forwarded_to_docker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []

    def fake_docker(
        arguments: Sequence[str],
        *,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        command = list(arguments)
        commands.append(command)
        if command[0] == "run":
            return _completed(command, stdout="container-456\n")
        if command[0] == "port":
            return _completed(command, stdout="127.0.0.1:49153\n")
        return _completed(command)

    monkeypatch.setattr(DockerWorkspace, "_docker", staticmethod(fake_docker))
    workspace = DockerWorkspace(
        image="gg-agent-server:dev",
        volumes=["/host/project:/workspace/project"],
    )
    workspace._client = httpx.Client(
        base_url="http://127.0.0.1:49153",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"status": "ok"})
        ),
    )

    with workspace:
        pass

    assert commands[0][-3:] == [
        "--volume",
        "/host/project:/workspace/project",
        "gg-agent-server:dev",
    ]


def test_health_wait_reports_container_exit_and_logs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []

    def fake_docker(
        arguments: Sequence[str],
        *,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        command = list(arguments)
        commands.append(command)
        if command[0] == "run":
            return _completed(command, stdout="dead-container\n")
        if command[0] == "port":
            return _completed(command, stdout="127.0.0.1:49154\n")
        if command[0] == "inspect":
            return _completed(command, stdout="false\n")
        if command[0] == "logs":
            return _completed(command, stdout="server failed to boot\n")
        if command[0] == "stop":
            return _completed(command, returncode=1)
        raise AssertionError(f"unexpected Docker command: {command}")

    def unavailable(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(DockerWorkspace, "_docker", staticmethod(fake_docker))
    workspace = DockerWorkspace(image="broken:dev", poll_interval=0)
    workspace._client = httpx.Client(
        base_url="http://127.0.0.1:49154",
        transport=httpx.MockTransport(unavailable),
    )

    with pytest.raises(DockerWorkspaceError, match="exited before") as exc_info:
        with workspace:
            pass

    assert "server failed to boot" in str(exc_info.value)
    assert [command[0] for command in commands] == [
        "run",
        "port",
        "inspect",
        "logs",
        "stop",
    ]
    assert workspace.container_id is None


def test_missing_docker_cli_has_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing_cli(*_: Any, **__: Any) -> None:
        raise FileNotFoundError

    monkeypatch.setattr(docker_module.subprocess, "run", missing_cli)

    with pytest.raises(DockerWorkspaceError, match="Docker CLI was not found"):
        with DockerWorkspace(image="gg-agent-server:dev"):
            pass
