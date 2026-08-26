"""Fake-runtime demo: dummy agent writes ``NOTES.md`` in a sandbox.

This is the Docker demo with its workspace constructor changed to::

    workspace = RuntimeWorkspace(
        runtime_api_url=runtime_api_url,
        runtime_api_key=runtime_api_key,
    )

The command starts the standalone runtime API, which starts the agent-server
container.  The SDK talks HTTP to both planes; only the runtime process talks
to Docker.  The demo inspects Docker solely to prove the file exists in the
sandbox and that the container is removed afterward.

Run it after building the image::

    docker build -t gg-agent-server:dev .
    uv run python -m gg.sdk.demo.runtime_notes
"""

from __future__ import annotations

import argparse
import os
import secrets
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import PurePosixPath

import httpx

from gg.sdk import Event, RemoteConversation, RuntimeWorkspace


DEFAULT_IMAGE = "gg-agent-server:dev"
DEFAULT_MESSAGE = "hello from the fake runtime demo"
DEFAULT_WORKING_DIR = "/workspace/project"
DEFAULT_RUNTIME_HOST = "127.0.0.1"

ContainerLister = Callable[[str], set[str]]
ContainerFileReader = Callable[[str, str], str]
WorkspaceFactory = Callable[..., RuntimeWorkspace]


@dataclass(frozen=True)
class RuntimeDemoResult:
    """Evidence captured across the provisioned sandbox lifecycle."""

    session_id: str
    container_id: str
    conversation_id: str
    notes_path: str
    notes_content: str
    events: list[Event]


def run_demo(
    *,
    runtime_api_url: str,
    runtime_api_key: str,
    image: str = DEFAULT_IMAGE,
    message: str = DEFAULT_MESSAGE,
    working_dir: str = DEFAULT_WORKING_DIR,
    workspace_factory: WorkspaceFactory = RuntimeWorkspace,
    container_lister: ContainerLister | None = None,
    container_file_reader: ContainerFileReader | None = None,
) -> RuntimeDemoResult:
    """Provision through the runtime, run the agent, and prove cleanup."""
    list_containers = container_lister or _running_image_containers
    read_container_file = container_file_reader or _read_container_file
    containers_before = list_containers(image)
    notes_path = str(PurePosixPath(working_dir) / "NOTES.md")

    with workspace_factory(
        runtime_api_url=runtime_api_url,
        runtime_api_key=runtime_api_key,
        working_dir=working_dir,
    ) as workspace:
        session_id = workspace.session_id
        if session_id is None:
            raise RuntimeError("RuntimeWorkspace did not expose its runtime session")

        new_containers = list_containers(image) - containers_before
        if len(new_containers) != 1:
            raise RuntimeError(
                "expected the runtime API to start exactly one sandbox container; "
                f"found {sorted(new_containers)!r}"
            )
        container_id = new_containers.pop()

        conversation = RemoteConversation(workspace=workspace)
        conversation.send_message(message)
        conversation.run()
        events = conversation.list_events()
        notes_content = read_container_file(container_id, notes_path)

    if container_id in list_containers(image):
        raise RuntimeError(
            f"runtime session {session_id} left container {container_id} running"
        )

    return RuntimeDemoResult(
        session_id=session_id,
        container_id=container_id,
        conversation_id=conversation.id,
        notes_path=notes_path,
        notes_content=notes_content,
        events=events,
    )


@contextmanager
def local_runtime_process(
    *,
    api_key: str,
    image: str,
    host: str = DEFAULT_RUNTIME_HOST,
    port: int | None = None,
    startup_timeout: float = 30.0,
) -> Iterator[tuple[str, subprocess.Popen[bytes]]]:
    """Start a local runtime API subprocess and always stop it on exit."""
    runtime_port = port or _available_port(host)
    runtime_url = f"http://{host}:{runtime_port}"
    environment = os.environ.copy()
    environment["GG_RUNTIME_API_KEY"] = api_key
    environment["GG_RUNTIME_IMAGE"] = image
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "gg.runtime",
            "--host",
            host,
            "--port",
            str(runtime_port),
        ],
        env=environment,
    )
    try:
        _wait_for_runtime(runtime_url, process, timeout=startup_timeout)
        yield runtime_url, process
    finally:
        _stop_process(process)


def _available_port(host: str) -> int:
    with socket.socket() as listener:
        listener.bind((host, 0))
        port = listener.getsockname()[1]
    return int(port)


def _wait_for_runtime(
    runtime_url: str,
    process: subprocess.Popen[bytes],
    *,
    timeout: float,
) -> None:
    deadline = time.monotonic() + timeout
    last_error = "runtime API did not respond"
    while time.monotonic() < deadline:
        return_code = process.poll()
        if return_code is not None:
            raise RuntimeError(
                f"runtime API process exited during startup with code {return_code}"
            )
        try:
            response = httpx.get(f"{runtime_url}/openapi.json", timeout=0.5)
            response.raise_for_status()
            return
        except httpx.HTTPError as exc:
            last_error = str(exc)
            time.sleep(0.1)
    raise RuntimeError(
        f"runtime API did not become ready within {timeout:g}s: {last_error}"
    )


def _stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _docker(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["docker", *arguments],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "Docker CLI was not found; install Docker and ensure `docker` is on PATH"
        ) from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "unknown Docker error").strip()
        raise RuntimeError(
            f"Docker command failed (`{' '.join(exc.cmd)}`): {detail}"
        ) from exc


def _running_image_containers(image: str) -> set[str]:
    result = _docker(["ps", "--quiet", "--filter", f"ancestor={image}"])
    return set(result.stdout.split())


def _read_container_file(container_id: str, path: str) -> str:
    result = _docker(["exec", container_id, "cat", path])
    return result.stdout


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the dummy agent through the fake runtime API."
    )
    parser.add_argument(
        "--image",
        default=DEFAULT_IMAGE,
        help=f"Agent-server image (default: {DEFAULT_IMAGE})",
    )
    args = parser.parse_args()
    runtime_api_key = secrets.token_urlsafe(32)

    with local_runtime_process(
        api_key=runtime_api_key,
        image=args.image,
    ) as (runtime_api_url, runtime_process):
        result = run_demo(
            runtime_api_url=runtime_api_url,
            runtime_api_key=runtime_api_key,
            image=args.image,
        )
        runtime_pid = runtime_process.pid

    if runtime_process.poll() is None:
        raise RuntimeError(f"runtime API process {runtime_pid} was not stopped")

    print(f"runtime session: {result.session_id}")
    print(f"sandbox: {result.container_id}:{result.notes_path}")
    print(result.notes_content, end="")


if __name__ == "__main__":
    main()
