"""Docker Pi demo: a remote Pi agent writes ``PI_NOTES.md`` in a container.

The workspace constructor is::

    workspace = DockerWorkspace(
        image="gg-agent-server:dev",
        secret_env_names=["OPENROUTER_API_KEY"],
    )
    conversation = RemoteConversation(
        workspace=workspace,
        agent=PiAgentConfig(
            kind="pi",
            provider="openrouter",
            model="google/gemini-3.7-flash",
        ),
    )

That starts an isolated agent-server container, forwards the host OpenRouter
key by name only, and drives a Pi conversation over HTTP. The demo reads
``/workspace/project/PI_NOTES.md`` with ``docker exec`` before the context
stops the container. No host directory is mounted.

Run it after building the image::

    docker build -t gg-agent-server:dev .
    export OPENROUTER_API_KEY=...
    uv run python -m gg.sdk.demo.docker_pi_notes
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import PurePosixPath
from uuid import uuid4

from gg.sdk import (
    ConversationStatus,
    DockerWorkspace,
    Event,
    EventKind,
    PiAgentConfig,
    RemoteConversation,
)


DEFAULT_IMAGE = "gg-agent-server:dev"
DEFAULT_WORKING_DIR = "/workspace/project"
NOTES_FILENAME = "PI_NOTES.md"
OPENROUTER_SECRET_NAME = "OPENROUTER_API_KEY"
PI_AGENT = PiAgentConfig(
    kind="pi",
    provider="openrouter",
    model="google/gemini-3.7-flash",
)
REQUIRED_EVENT_KINDS = frozenset(
    {
        EventKind.MESSAGE,
        EventKind.ACTION,
        EventKind.OBSERVATION,
        EventKind.STATUS,
    }
)

ContainerFileReader = Callable[[str, str], str]
WorkspaceFactory = Callable[..., DockerWorkspace]


@dataclass(frozen=True)
class DockerPiDemoResult:
    """Evidence captured before the demo container is stopped."""

    container_id: str
    conversation_id: str
    conversation_status: ConversationStatus
    notes_path: str
    notes_content: str
    marker: str
    events: list[Event]


def run_demo(
    *,
    image: str = DEFAULT_IMAGE,
    working_dir: str = DEFAULT_WORKING_DIR,
    marker: str | None = None,
    workspace_factory: WorkspaceFactory = DockerWorkspace,
    container_file_reader: ContainerFileReader | None = None,
) -> DockerPiDemoResult:
    """Run Pi remotely, prove the marked file, and always stop the container."""
    _require_openrouter_key()
    notes_path = str(PurePosixPath(working_dir) / NOTES_FILENAME)
    unique_marker = marker if marker is not None else f"GG_DOCKER_PI_DEMO_{uuid4().hex}"
    prompt = (
        f"Create the file {notes_path}. "
        f"The file must contain this exact unique marker: {unique_marker}. "
        "After writing it, briefly confirm what you did."
    )
    reader = container_file_reader or _read_container_file

    with workspace_factory(
        image=image,
        working_dir=working_dir,
        secret_env_names=[OPENROUTER_SECRET_NAME],
        timeout=float(PI_AGENT.timeout_seconds),
    ) as workspace:
        conversation = RemoteConversation(workspace=workspace, agent=PI_AGENT)
        conversation.send_message(prompt)
        conversation.run()
        if conversation.status != ConversationStatus.FINISHED:
            raise RuntimeError(
                "Pi conversation did not finish successfully "
                f"(status={conversation.status})"
            )

        container_id = workspace.container_id
        if container_id is None:
            raise RuntimeError("DockerWorkspace did not expose its running container")

        notes_content = reader(container_id, notes_path)
        if unique_marker not in notes_content:
            raise RuntimeError(f"{notes_path} does not contain the requested marker")

        events = conversation.list_events()
        _assert_required_events(events)
        _assert_secret_absent(
            {
                "notes_content": notes_content,
                "events": [event.model_dump(mode="json") for event in events],
            }
        )

    return DockerPiDemoResult(
        container_id=container_id,
        conversation_id=conversation.id,
        conversation_status=conversation.status,
        notes_path=notes_path,
        notes_content=notes_content,
        marker=unique_marker,
        events=events,
    )


def _require_openrouter_key() -> None:
    if not os.environ.get(OPENROUTER_SECRET_NAME):
        raise RuntimeError(
            f"{OPENROUTER_SECRET_NAME} must be set on the host before the "
            "Docker Pi demo"
        )


def _assert_required_events(events: list[Event]) -> None:
    present = {event.kind for event in events}
    missing = sorted(kind.value for kind in REQUIRED_EVENT_KINDS - present)
    if missing:
        raise RuntimeError(
            "conversation is missing required event kinds: " + ", ".join(missing)
        )


def _assert_secret_absent(value: object) -> None:
    secret = os.environ.get(OPENROUTER_SECRET_NAME)
    if not secret:
        return
    dumped = json.dumps(value, default=str)
    if secret in dumped:
        raise RuntimeError("OpenRouter API key leaked into demo evidence")


def _redact_secret(text: str) -> str:
    secret = os.environ.get(OPENROUTER_SECRET_NAME)
    if secret:
        return text.replace(secret, "[REDACTED]")
    return text


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

    detail = _redact_secret(
        (result.stderr or result.stdout or "file was not readable").strip()
    )
    raise RuntimeError(
        f"{NOTES_FILENAME} was not found in container {container_id} at "
        f"{path}: {detail}"
    )


def _event_summary(events: list[Event]) -> str:
    counts = Counter(event.kind.value for event in events)
    return ", ".join(f"{kind}={counts[kind]}" for kind in sorted(counts))


def _print_output(text: str) -> None:
    print(_redact_secret(text), end="" if text.endswith("\n") else "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a Pi agent in a Docker-backed gg-agent-server."
    )
    parser.add_argument(
        "--image",
        default=DEFAULT_IMAGE,
        help=f"Agent-server image (default: {DEFAULT_IMAGE})",
    )
    args = parser.parse_args()

    result = run_demo(image=args.image)
    print(f"{result.container_id}:{result.notes_path}")
    print("File contents:")
    _print_output(result.notes_content)
    print(f"Conversation: {result.conversation_id} ({result.conversation_status})")
    print(f"Persisted events ({len(result.events)}): {_event_summary(result.events)}")


if __name__ == "__main__":
    main()
