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


def test_openrouter_secret_is_forwarded_by_name_with_host_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "openrouter-test-secret"
    docker_calls: list[tuple[list[str], dict[str, str] | None, tuple[str, ...]]] = []

    def fake_docker(
        arguments: Sequence[str],
        *,
        check: bool = True,
        env: dict[str, str] | None = None,
        redact_values: Sequence[str] = (),
    ) -> subprocess.CompletedProcess[str]:
        command = list(arguments)
        docker_calls.append((command, env, tuple(redact_values)))
        if command[0] == "run":
            return _completed(command, stdout="container-secret\n")
        if command[0] == "port":
            return _completed(command, stdout="127.0.0.1:49155\n")
        return _completed(command)

    monkeypatch.setenv("OPENROUTER_API_KEY", secret)
    monkeypatch.setattr(DockerWorkspace, "_docker", staticmethod(fake_docker))
    workspace = DockerWorkspace(
        image="gg-agent-server:dev",
        secret_env_names=["OPENROUTER_API_KEY"],
    )
    workspace._client = httpx.Client(
        base_url="http://127.0.0.1:49155",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"status": "ok"})
        ),
    )

    with workspace:
        pass

    run_command, environment, redacted_values = docker_calls[0]
    assert run_command[-3:] == [
        "--env",
        "OPENROUTER_API_KEY",
        "gg-agent-server:dev",
    ]
    assert secret not in repr(run_command)
    assert environment is not None
    assert environment["OPENROUTER_API_KEY"] == secret
    assert redacted_values == (secret,)
    assert secret not in repr(workspace)


def test_unsupported_secret_environment_name_is_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="unsupported secret environment name: OTHER_KEY",
    ):
        DockerWorkspace(
            image="gg-agent-server:dev",
            secret_env_names=["OTHER_KEY"],
        )


@pytest.mark.parametrize("value", [None, ""])
def test_requested_openrouter_secret_must_be_present_before_docker_run(
    monkeypatch: pytest.MonkeyPatch,
    value: str | None,
) -> None:
    docker_was_called = False

    def fake_docker(*_: Any, **__: Any) -> None:
        nonlocal docker_was_called
        docker_was_called = True

    if value is None:
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    else:
        monkeypatch.setenv("OPENROUTER_API_KEY", value)
    monkeypatch.setattr(DockerWorkspace, "_docker", staticmethod(fake_docker))
    workspace = DockerWorkspace(
        image="gg-agent-server:dev",
        secret_env_names=["OPENROUTER_API_KEY"],
    )

    with pytest.raises(DockerWorkspaceError, match="missing or empty"):
        with workspace:
            pass

    assert not docker_was_called


@pytest.mark.parametrize("name", ["GH_TOKEN", "GITHUB_TOKEN"])
def test_github_secret_environment_name_is_accepted(name: str) -> None:
    workspace = DockerWorkspace(
        image="gg-agent-server:dev",
        secret_env_names=[name],
    )
    assert workspace.secret_env_names == (name,)


def test_multiple_secrets_are_forwarded_by_name_in_one_docker_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    openrouter_secret = "openrouter-test-secret"
    gh_secret = "gh-test-secret"
    github_secret = "github-test-secret"
    docker_calls: list[tuple[list[str], dict[str, str] | None, tuple[str, ...]]] = []

    def fake_docker(
        arguments: Sequence[str],
        *,
        check: bool = True,
        env: dict[str, str] | None = None,
        redact_values: Sequence[str] = (),
    ) -> subprocess.CompletedProcess[str]:
        command = list(arguments)
        docker_calls.append((command, env, tuple(redact_values)))
        if command[0] == "run":
            return _completed(command, stdout="container-multi-secret\n")
        if command[0] == "port":
            return _completed(command, stdout="127.0.0.1:49156\n")
        return _completed(command)

    monkeypatch.setenv("OPENROUTER_API_KEY", openrouter_secret)
    monkeypatch.setenv("GH_TOKEN", gh_secret)
    monkeypatch.setenv("GITHUB_TOKEN", github_secret)
    monkeypatch.setattr(DockerWorkspace, "_docker", staticmethod(fake_docker))
    workspace = DockerWorkspace(
        image="gg-agent-server:dev",
        secret_env_names=["OPENROUTER_API_KEY", "GH_TOKEN", "GITHUB_TOKEN"],
    )
    workspace._client = httpx.Client(
        base_url="http://127.0.0.1:49156",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"status": "ok"})
        ),
    )

    with workspace:
        pass

    run_command, environment, redacted_values = docker_calls[0]
    assert run_command == [
        "run",
        "--detach",
        "--rm",
        "--publish",
        "127.0.0.1::8000",
        "--env",
        "OPENROUTER_API_KEY",
        "--env",
        "GH_TOKEN",
        "--env",
        "GITHUB_TOKEN",
        "gg-agent-server:dev",
    ]
    for secret in (openrouter_secret, gh_secret, github_secret):
        assert secret not in repr(run_command)
        assert secret not in repr(workspace)
    assert environment is not None
    assert environment["OPENROUTER_API_KEY"] == openrouter_secret
    assert environment["GH_TOKEN"] == gh_secret
    assert environment["GITHUB_TOKEN"] == github_secret
    assert redacted_values == (openrouter_secret, gh_secret, github_secret)


@pytest.mark.parametrize("name", ["GH_TOKEN", "GITHUB_TOKEN"])
@pytest.mark.parametrize("value", [None, ""])
def test_requested_github_secret_must_be_present_before_docker_run(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: str | None,
) -> None:
    docker_was_called = False

    def fake_docker(*_: Any, **__: Any) -> None:
        nonlocal docker_was_called
        docker_was_called = True

    monkeypatch.setenv("OPENROUTER_API_KEY", "present-openrouter-secret")
    if value is None:
        monkeypatch.delenv(name, raising=False)
    else:
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(DockerWorkspace, "_docker", staticmethod(fake_docker))
    workspace = DockerWorkspace(
        image="gg-agent-server:dev",
        secret_env_names=["OPENROUTER_API_KEY", name],
    )

    with pytest.raises(
        DockerWorkspaceError,
        match=f"requested secret environment variable is missing or empty: {name}",
    ):
        with workspace:
            pass

    assert not docker_was_called


def test_docker_failure_redacts_forwarded_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "openrouter-must-not-leak"

    def failed_run(command: list[str], **_: Any) -> None:
        raise subprocess.CalledProcessError(
            125,
            command,
            stderr=f"daemon rejected {secret}",
        )

    monkeypatch.setenv("OPENROUTER_API_KEY", secret)
    monkeypatch.setattr(docker_module.subprocess, "run", failed_run)
    workspace = DockerWorkspace(
        image="gg-agent-server:dev",
        secret_env_names=["OPENROUTER_API_KEY"],
    )

    with pytest.raises(DockerWorkspaceError) as exc_info:
        with workspace:
            pass

    assert secret not in str(exc_info.value)
    assert "[REDACTED]" in str(exc_info.value)


def test_docker_failure_redacts_every_forwarded_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    openrouter_secret = "openrouter-must-not-leak"
    gh_secret = "gh-must-not-leak"
    github_secret = "github-must-not-leak"

    def failed_run(command: list[str], **_: Any) -> None:
        raise subprocess.CalledProcessError(
            125,
            command,
            stderr=(
                f"daemon rejected {openrouter_secret} {gh_secret} {github_secret}"
            ),
        )

    monkeypatch.setenv("OPENROUTER_API_KEY", openrouter_secret)
    monkeypatch.setenv("GH_TOKEN", gh_secret)
    monkeypatch.setenv("GITHUB_TOKEN", github_secret)
    monkeypatch.setattr(docker_module.subprocess, "run", failed_run)
    workspace = DockerWorkspace(
        image="gg-agent-server:dev",
        secret_env_names=["OPENROUTER_API_KEY", "GH_TOKEN", "GITHUB_TOKEN"],
    )

    with pytest.raises(DockerWorkspaceError) as exc_info:
        with workspace:
            pass

    message = str(exc_info.value)
    representation = repr(exc_info.value)
    for secret in (openrouter_secret, gh_secret, github_secret):
        assert secret not in message
        assert secret not in representation
    assert message.count("[REDACTED]") == 3


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
