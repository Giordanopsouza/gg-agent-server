"""Host-side repository preparation for finalization."""

from __future__ import annotations

import base64
import subprocess
from pathlib import Path

from gg.sdk.task_execution import TaskResultManifest


class RepoPrepError(RuntimeError):
    """Repository preparation failed on the control plane."""


def prepare_repo_from_manifest(
    manifest: TaskResultManifest,
    *,
    destination: Path,
    github_token: str,
    process_env: dict[str, str],
) -> None:
    """Clone and materialize one task branch from archived manifest evidence."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and any(destination.iterdir()):
        raise RepoPrepError(f"destination {destination} is not empty")
    env = _clone_env(process_env, github_token)
    completed = subprocess.run(
        [
            "git",
            "clone",
            "--",
            f"https://github.com/{manifest.repository}.git",
            str(destination),
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip().replace(github_token, "[REDACTED]")
        detail = detail.replace(
            env["GIT_CONFIG_VALUE_0"].rsplit(" ", 1)[-1], "[REDACTED]"
        )
        raise RepoPrepError(f"clone failed for {manifest.repository}: {detail}")
    local_env = _local_git_env(process_env)
    _run_git(
        ["git", "checkout", "-B", manifest.task_branch, manifest.base_sha],
        cwd=destination,
        env=local_env,
    )
    if manifest.patch and manifest.changed_files:
        patch_path = destination / ".gg-task.patch"
        patch_path.write_text(manifest.patch, encoding="utf-8")
        _run_git(
            ["git", "apply", str(patch_path)],
            cwd=destination,
            env=local_env,
        )
        patch_path.unlink(missing_ok=True)


def _local_git_env(process_env: dict[str, str]) -> dict[str, str]:
    env = dict(process_env)
    env.pop("GH_TOKEN", None)
    env.pop("GG_GITHUB_CLONE_TOKEN", None)
    env.pop("GIT_CONFIG_COUNT", None)
    env.pop("GIT_CONFIG_PARAMETERS", None)
    for key in list(env):
        if key.startswith(("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")):
            env.pop(key)
    return env


def _clone_env(process_env: dict[str, str], token: str) -> dict[str, str]:
    if not token:
        raise RepoPrepError("github token is required to clone the repository")
    env = _local_git_env(process_env)
    credential = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    env["GIT_CONFIG_COUNT"] = "1"
    env["GIT_CONFIG_KEY_0"] = "http.https://github.com/.extraheader"
    env["GIT_CONFIG_VALUE_0"] = f"Authorization: Basic {credential}"
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def _run_git(args: list[str], *, cwd: Path, env: dict[str, str]) -> None:
    completed = subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    if completed.returncode != 0:
        raise RepoPrepError(completed.stderr.strip() or completed.stdout.strip())


__all__ = ["RepoPrepError", "prepare_repo_from_manifest"]
