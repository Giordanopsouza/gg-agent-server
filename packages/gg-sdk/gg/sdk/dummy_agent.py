from __future__ import annotations

from typing import Any


def plan_write_notes(*, user_message: str) -> dict[str, Any]:
    """Dummy agent: always one write_file action for NOTES.md."""

    return {
        "tool": "write_file",
        "args": {
            "path": "NOTES.md",
            "content": f"# Notes\n\n{user_message}\n",
        },
    }
