from __future__ import annotations

import subprocess
from pathlib import Path

from pydantic import BaseModel


class CommandResult(BaseModel):
    """What comes back after running a shell command."""

    command: str
    exit_code: int
    stdout: str
    stderr: str


class LocalWorkspace:
    """In-process workspace rooted at working_dir on the host disk."""

    # Remember the root folder and create it if it does not exist yet.
    def __init__(self, *, working_dir: str | Path) -> None:
        self.working_dir = Path(working_dir)
        self.working_dir.mkdir(parents=True, exist_ok=True)

    # Relative paths stay inside working_dir; absolute paths are used as-is.
    def _resolve_path(self, path: str | Path) -> Path:
        candidate = Path(path)
        if candidate.is_absolute():
            return candidate
        return self.working_dir / candidate

    # Create parent folders, then write bytes to disk.
    def write_file(self, path: str | Path, content: str | bytes) -> None:
        target = self._resolve_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        data = content.encode() if isinstance(content, str) else content
        target.write_bytes(data)

    # Read the file back as raw bytes.
    def read_file(self, path: str | Path) -> bytes:
        return self._resolve_path(path).read_bytes()

    # Run a shell command; default cwd is working_dir, not the process cwd.
    def execute_command(
        self,
        command: str,
        *,
        cwd: str | Path | None = None,
        timeout: float = 30.0,
    ) -> CommandResult:
        run_cwd = Path(cwd) if cwd is not None else self.working_dir
        completed = subprocess.run(
            command,
            shell=True,
            cwd=run_cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return CommandResult(
            command=command,
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
