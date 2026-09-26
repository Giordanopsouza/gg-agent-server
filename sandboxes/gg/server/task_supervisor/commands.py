"""Bounded shell execution for bootstrap and check commands."""

from __future__ import annotations

import subprocess
import time
from collections.abc import Mapping

from gg.sdk.task_execution import CommandCapture


def run_bounded_command(
    *,
    command: str,
    cwd: str,
    timeout_seconds: float,
    max_output_bytes: int,
    process_env: Mapping[str, str],
    extra_env: Mapping[str, str] | None = None,
) -> CommandCapture:
    """Run one command with timeout and truncated stdout/stderr capture."""

    env = dict(process_env)
    if extra_env is not None:
        env.update(extra_env)
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=env,
        )
        duration_ms = int((time.monotonic() - started) * 1000)
        stdout, stdout_truncated = _truncate(completed.stdout, max_output_bytes)
        stderr, stderr_truncated = _truncate(completed.stderr, max_output_bytes)
        return CommandCapture(
            command=command,
            exit_code=completed.returncode,
            duration_ms=duration_ms,
            stdout=stdout,
            stderr=stderr,
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
            timed_out=False,
        )
    except subprocess.TimeoutExpired as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        stdout, stdout_truncated = _truncate(
            exc.stdout.decode() if isinstance(exc.stdout, bytes) else exc.stdout or "",
            max_output_bytes,
        )
        stderr, stderr_truncated = _truncate(
            exc.stderr.decode() if isinstance(exc.stderr, bytes) else exc.stderr or "",
            max_output_bytes,
        )
        return CommandCapture(
            command=command,
            exit_code=None,
            duration_ms=duration_ms,
            stdout=stdout,
            stderr=stderr,
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
            timed_out=True,
        )


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= limit:
        return text, False
    clipped = encoded[:limit].decode("utf-8", errors="ignore")
    return clipped, True


__all__ = ["run_bounded_command"]
