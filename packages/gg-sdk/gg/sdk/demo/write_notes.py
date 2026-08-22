"""In-process demo: dummy agent writes NOTES.md with no server."""

from __future__ import annotations

import tempfile
from pathlib import Path

from gg.sdk import LocalConversation, LocalWorkspace


DEFAULT_MESSAGE = "hello from the in-process demo"


def run_demo(
    base_dir: Path | str | None = None,
    *,
    message: str = DEFAULT_MESSAGE,
) -> tuple[Path, Path]:
    """Create workspace dirs, run the conversation loop, return paths.

    Returns ``(notes_path, conversation_dir)``. When ``base_dir`` is omitted,
    a new temp directory is created and left on disk so you can open NOTES.md.
    """
    root = Path(base_dir) if base_dir is not None else Path(
        tempfile.mkdtemp(prefix="gg-write-notes-")
    )
    workspace_dir = root / "workspace"
    conversation_dir = root / "conversation"

    workspace = LocalWorkspace(working_dir=workspace_dir)
    conversation = LocalConversation(
        conversation_dir=conversation_dir,
        workspace=workspace,
    )
    conversation.send_message(message)
    conversation.run()

    notes_path = workspace.working_dir / "NOTES.md"
    return notes_path, conversation_dir


def main() -> None:
    notes_path, _ = run_demo()
    print(notes_path)


if __name__ == "__main__":
    main()
