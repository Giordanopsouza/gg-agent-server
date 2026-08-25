from __future__ import annotations

import subprocess
import time
from collections.abc import Sequence
from pathlib import Path

import httpx

from gg.sdk.remote_workspace import RemoteWorkspace


_CONTAINER_PORT = "8000/tcp"


class DockerWorkspaceError(RuntimeError):
    """Raised when Docker cannot start a usable agent-server workspace."""


class DockerWorkspace(RemoteWorkspace):
    """A remote workspace backed by one locally managed Docker container.

    Constructing the workspace has no side effects. Enter its context to start
    the container and make ``host`` reachable; leaving the context stops it.
    Host directories are only mounted when explicitly listed in ``volumes``.
    """

    def __init__(
        self,
        *,
        image: str,
        working_dir: str | Path = "/workspace/project",
        api_key: str | None = None,
        volumes: Sequence[str] | None = None,
        timeout: float = 30.0,
        health_timeout: float = 30.0,
        poll_interval: float = 0.1,
    ) -> None:
        if not image.strip():
            raise ValueError("image must not be empty")
        if api_key is not None and (
            not api_key or api_key != api_key.strip() or "," in api_key
        ):
            raise ValueError(
                "api_key must be non-empty and cannot contain commas or surrounding "
                "whitespace"
            )
        if health_timeout < 0:
            raise ValueError("health_timeout must be non-negative")
        if poll_interval < 0:
            raise ValueError("poll_interval must be non-negative")

        # Docker chooses the real port on entry. Port zero keeps this object a
        # valid RemoteWorkspace without claiming that it is reachable yet.
        super().__init__(
            host="http://127.0.0.1:0",
            working_dir=working_dir,
            api_key=api_key,
            timeout=timeout,
        )
        self.image = image
        self.volumes = tuple(volumes or ())
        self.health_timeout = health_timeout
        self.poll_interval = poll_interval
        self.container_id: str | None = None

    def __enter__(self) -> DockerWorkspace:
        if self.container_id is not None:
            raise RuntimeError("DockerWorkspace is already running")

        command = [
            "docker",
            "run",
            "--detach",
            "--rm",
            "--publish",
            "127.0.0.1::8000",
        ]
        if self.api_key is not None:
            command.extend(["--env", f"GG_SESSION_API_KEYS={self.api_key}"])
        for volume in self.volumes:
            command.extend(["--volume", volume])
        command.append(self.image)

        try:
            result = self._docker(command[1:])
            self.container_id = result.stdout.strip()
            if not self.container_id:
                raise DockerWorkspaceError("docker run returned no container id")
            port_result = self._docker(
                ["port", self.container_id, _CONTAINER_PORT]
            )
            port = _published_port(port_result.stdout)
            self.host = f"http://127.0.0.1:{port}"
            self._wait_until_healthy()
        except BaseException:
            self.stop()
            raise
        return self

    def __exit__(self, *_: object) -> None:
        self.stop()

    def stop(self) -> None:
        """Close the HTTP client and stop the owned container, if any."""
        self.close()
        container_id = self.container_id
        self.container_id = None
        if container_id is not None:
            self._docker(["stop", container_id], check=False)

    def _wait_until_healthy(self) -> None:
        deadline = time.monotonic() + self.health_timeout
        last_error = "health endpoint did not respond"

        while True:
            try:
                remaining = max(deadline - time.monotonic(), 0.001)
                response = self.client.get(
                    "/health",
                    timeout=min(self.timeout, remaining),
                )
                response.raise_for_status()
                return
            except httpx.HTTPError as exc:
                last_error = str(exc)

            if not self._container_is_running():
                logs = self._container_logs()
                detail = f" Container logs:\n{logs}" if logs else ""
                raise DockerWorkspaceError(
                    f"agent-server container {self.container_id} exited before "
                    f"becoming healthy.{detail}"
                )
            if time.monotonic() >= deadline:
                raise DockerWorkspaceError(
                    f"agent-server container {self.container_id} did not become "
                    f"healthy within {self.health_timeout:g}s: {last_error}"
                )
            time.sleep(self.poll_interval)

    def _container_is_running(self) -> bool:
        result = self._docker(
            ["inspect", "--format", "{{.State.Running}}", self._container_id()],
            check=False,
        )
        return result.returncode == 0 and result.stdout.strip() == "true"

    def _container_logs(self) -> str:
        result = self._docker(
            ["logs", self._container_id()],
            check=False,
        )
        return "\n".join(
            output.strip()
            for output in (result.stdout, result.stderr)
            if output.strip()
        )

    def _container_id(self) -> str:
        if self.container_id is None:
            raise DockerWorkspaceError("Docker container has not been started")
        return self.container_id

    @staticmethod
    def _docker(
        arguments: Sequence[str],
        *,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                ["docker", *arguments],
                check=check,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as exc:
            raise DockerWorkspaceError(
                "Docker CLI was not found; install Docker and ensure `docker` is "
                "on PATH"
            ) from exc
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or "unknown Docker error").strip()
            raise DockerWorkspaceError(
                f"Docker command failed (`{' '.join(exc.cmd)}`): {detail}"
            ) from exc


def _published_port(output: str) -> int:
    """Parse Docker's host mapping for a port bound to IPv4 loopback."""
    mapping = output.strip().splitlines()
    if len(mapping) != 1:
        raise DockerWorkspaceError(
            f"expected one published port for {_CONTAINER_PORT}, got {output!r}"
        )
    host, separator, raw_port = mapping[0].rpartition(":")
    if not separator or host != "127.0.0.1":
        raise DockerWorkspaceError(
            f"unexpected published port mapping: {mapping[0]!r}"
        )
    try:
        return int(raw_port)
    except ValueError as exc:
        raise DockerWorkspaceError(
            f"invalid published port mapping: {mapping[0]!r}"
        ) from exc
