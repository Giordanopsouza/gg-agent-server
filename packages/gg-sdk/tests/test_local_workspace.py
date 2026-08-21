from __future__ import annotations

from pathlib import Path

from gg.sdk import CommandResult, LocalWorkspace


# write_file should create nested folders and leave bytes on disk.
def test_write_file_creates_parents_and_bytes_on_disk(tmp_path: Path) -> None:
    workspace = LocalWorkspace(working_dir=tmp_path / "agent-home")
    workspace.write_file("notes/todo.txt", "buy milk")

    file_path = tmp_path / "agent-home" / "notes" / "todo.txt"
    assert file_path.exists()
    assert file_path.read_bytes() == b"buy milk"


# read_file should return the same bytes that write_file stored.
def test_read_file_returns_bytes_just_written(tmp_path: Path) -> None:
    workspace = LocalWorkspace(working_dir=tmp_path / "agent-home")
    workspace.write_file("hello.txt", b"\x00\xff")

    assert workspace.read_file("hello.txt") == b"\x00\xff"


# execute_command with no cwd should run inside working_dir.
def test_execute_command_defaults_cwd_to_working_dir(tmp_path: Path) -> None:
    workspace = LocalWorkspace(working_dir=tmp_path / "agent-home")

    result = workspace.execute_command("pwd")

    assert isinstance(result, CommandResult)
    assert result.exit_code == 0
    assert Path(result.stdout.strip()).resolve() == workspace.working_dir.resolve()
