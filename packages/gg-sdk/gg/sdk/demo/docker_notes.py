"""Docker sandbox demo: dummy agent writes ``NOTES.md`` in a container.

The one workspace-constructor change from the local demo is::

    workspace = DockerWorkspace(image="gg-agent-server:dev")

That starts an agent server in a fresh container.  The demo uses
``RemoteConversation`` to drive it, reads the resulting file with
``docker exec``, and stops the container when the context exits.  No host
directory is mounted by default.

Run it after building the image::

    docker build -t gg-agent-server:dev .
    uv run python -m gg.sdk.demo.docker_notes
"""

from __future__ import annotations

import argparse
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import PurePosixPath

from gg.sdk import DockerWorkspace, Event, RemoteConversation


DEFAULT_IMAGE = "gg-agent-server:dev"
DEFAULT_MESSAGE = "hello from the Docker sandbox demo"
DEFAULT_WORKING_DIR = "/workspace/project"

ContainerFileReader = Callable[[str, str], str]
WorkspaceFactory = Callable[..., DockerWorkspace]


@dataclass(frozen=True)
class DockerDemoResult:
    """Evidence captured before the demo container is stopped."""

    container_id: str
    conversation_id: str
    notes_path: str
    notes_content: str
    events: list[Event]


def run_demo(
    *,
    image: str = DEFAULT_IMAGE,
    message: str = DEFAULT_MESSAGE,
    working_dir: str = DEFAULT_WORKING_DIR,
    workspace_factory: WorkspaceFactory = DockerWorkspace,
    container_file_reader: ContainerFileReader | None = None,
) -> DockerDemoResult:
    """Run the dummy agent remotely and read its note from the container."""
    notes_path = str(PurePosixPath(working_dir) / "NOTES.md")
    reader = container_file_reader or _read_container_file

    with workspace_factory(image=image, working_dir=working_dir) as workspace:
        conversation = RemoteConversation(workspace=workspace)
        conversation.send_message(message)
        conversation.run()
        events = conversation.list_events()

        container_id = workspace.container_id
        if container_id is None:
            raise RuntimeError("DockerWorkspace did not expose its running container")
        notes_content = reader(container_id, notes_path)

    return DockerDemoResult(
        container_id=container_id,
        conversation_id=conversation.id,
        notes_path=notes_path,
        notes_content=notes_content,
        events=events,
    )


def _read_container_file(container_id: str, path: str) -> str:
    """Return a UTF-8 file from a running container or raise a useful error."""
    result = subprocess.run(
        ["docker", "exec", container_id, "cat", path],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return result.stdout

    detail = (result.stderr or result.stdout or "file was not readable").strip()
    raise RuntimeError(
        f"NOTES.md was not found in container {container_id} at {path}: {detail}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the dummy agent in a Docker-backed gg-agent-server."
    )
    parser.add_argument(
        "--image",
        default=DEFAULT_IMAGE,
        help=f"Agent-server image (default: {DEFAULT_IMAGE})",
    )
    args = parser.parse_args()

    result = run_demo(image=args.image)
    print(f"{result.container_id}:{result.notes_path}")
    print(result.notes_content, end="")


if __name__ == "__main__":
    main()
