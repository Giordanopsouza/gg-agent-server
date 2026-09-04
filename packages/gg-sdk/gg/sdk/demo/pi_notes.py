"""In-process Pi demo: a real agent writes ``PI_NOTES.md`` with no server.

Install the pinned Pi CLI and provide an OpenRouter API key before running::

    npm install -g --ignore-scripts @earendil-works/pi-coding-agent@0.83.0
    export OPENROUTER_API_KEY=...
    uv run --no-editable python -m gg.sdk.demo.pi_notes

The default workspace is a new temporary directory that is intentionally left
on disk for inspection. Pass ``--workspace PATH`` to use a specific directory.
"""

from __future__ import annotations

import argparse
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from gg.sdk import (
    AgentBackend,
    Event,
    EventKind,
    LocalConversation,
    LocalWorkspace,
    PiRpcAgent,
)


NOTES_FILENAME = "PI_NOTES.md"


@dataclass(frozen=True)
class PiNotesResult:
    """Files and persisted conversation evidence produced by the demo."""

    workspace_path: Path
    conversation_dir: Path
    notes_path: Path
    notes_content: str
    marker: str
    final_assistant_text: str
    events: list[Event]


def run_demo(
    workspace_path: Path | str | None = None,
    *,
    agent_backend: AgentBackend | None = None,
    marker: str | None = None,
) -> PiNotesResult:
    """Ask Pi to write a uniquely marked file in a local workspace."""
    workspace_dir = (
        Path(workspace_path)
        if workspace_path is not None
        else Path(tempfile.mkdtemp(prefix="gg-pi-notes-"))
    )
    unique_marker = marker if marker is not None else f"GG_PI_DEMO_{uuid4().hex}"
    prompt = (
        f"Create a file named {NOTES_FILENAME} in the current workspace. "
        f"The file must contain this exact unique marker: {unique_marker}. "
        "After writing it, briefly confirm what you did."
    )

    workspace = LocalWorkspace(working_dir=workspace_dir)
    conversation_dir = workspace.working_dir / ".gg" / "conversations" / uuid4().hex
    conversation = LocalConversation(
        conversation_dir=conversation_dir,
        workspace=workspace,
        agent_backend=agent_backend if agent_backend is not None else PiRpcAgent(),
    )
    conversation.send_message(prompt)
    conversation.run()

    notes_path = workspace.working_dir / NOTES_FILENAME
    try:
        notes_content = notes_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise RuntimeError(f"Pi did not create {notes_path}") from exc
    if unique_marker not in notes_content:
        raise RuntimeError(f"{notes_path} does not contain the requested marker")

    events = conversation.list_events()
    final_assistant_text = _final_assistant_text(events)
    return PiNotesResult(
        workspace_path=workspace.working_dir,
        conversation_dir=conversation_dir,
        notes_path=notes_path,
        notes_content=notes_content,
        marker=unique_marker,
        final_assistant_text=final_assistant_text,
        events=events,
    )


def _final_assistant_text(events: list[Event]) -> str:
    for event in reversed(events):
        if event.kind != EventKind.MESSAGE:
            continue
        if event.payload.get("role") != "assistant":
            continue
        text = event.payload.get("text")
        if isinstance(text, str):
            return text
    return ""


def _event_summary(events: list[Event]) -> str:
    counts = Counter(event.kind.value for event in events)
    return ", ".join(f"{kind}={counts[kind]}" for kind in sorted(counts))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ask a local Pi RPC agent to create PI_NOTES.md."
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        help="Workspace directory (default: a new temporary directory)",
    )
    args = parser.parse_args()

    result = run_demo(args.workspace)
    print(f"Workspace: {result.workspace_path}")
    print(f"File: {result.notes_path}")
    print("File contents:")
    print(result.notes_content, end="" if result.notes_content.endswith("\n") else "\n")
    print("Final assistant text:")
    print(result.final_assistant_text or "(none)")
    print(f"Persisted events ({len(result.events)}): {_event_summary(result.events)}")


if __name__ == "__main__":
    main()
