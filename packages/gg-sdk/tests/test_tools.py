from __future__ import annotations

from pathlib import Path

import pytest

from gg.sdk import (
    LocalWorkspace,
    Observation,
    ToolNotFoundError,
    WriteFileTool,
    default_tool_registry,
)


# write_file tool should leave bytes on disk and report what it wrote.
def test_write_file_tool_writes_disk_and_returns_observation(tmp_path: Path) -> None:
    workspace = LocalWorkspace(working_dir=tmp_path / "agent-home")
    tool = WriteFileTool()

    observation = tool.run(
        {"path": "notes/todo.txt", "content": "buy milk"},
        workspace,
    )

    file_path = tmp_path / "agent-home" / "notes" / "todo.txt"
    assert file_path.exists()
    assert file_path.read_bytes() == b"buy milk"
    assert observation == Observation(
        payload={"path": "notes/todo.txt", "bytes_written": 8},
    )


# default registry should include write_file and run it successfully.
def test_default_tool_registry_runs_write_file(tmp_path: Path) -> None:
    workspace = LocalWorkspace(working_dir=tmp_path / "agent-home")
    registry = default_tool_registry()

    observation = registry.run(
        "write_file",
        {"path": "NOTES.md", "content": "# notes"},
        workspace,
    )

    file_path = tmp_path / "agent-home" / "NOTES.md"
    assert file_path.read_text() == "# notes"
    assert observation.payload["path"] == "NOTES.md"


# unknown tool names should fail in the registry before touching the workspace.
def test_tool_registry_rejects_unknown_tool(tmp_path: Path) -> None:
    workspace = LocalWorkspace(working_dir=tmp_path / "agent-home")
    registry = default_tool_registry()

    with pytest.raises(ToolNotFoundError, match="unknown tool: bash"):
        registry.run("bash", {"command": "pwd"}, workspace)

    assert not any((tmp_path / "agent-home").iterdir())


# write_file should reject missing or mistyped args before calling the workspace.
def test_write_file_tool_validates_args(tmp_path: Path) -> None:
    workspace = LocalWorkspace(working_dir=tmp_path / "agent-home")
    tool = WriteFileTool()

    with pytest.raises(ValueError, match="path"):
        tool.run({"content": "hi"}, workspace)

    with pytest.raises(TypeError, match="content"):
        tool.run({"path": "x.txt", "content": 42}, workspace)
