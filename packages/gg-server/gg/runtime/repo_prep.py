"""Host-side repository preparation for finalization."""

from __future__ import annotations

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
    env = dict(process_env)
    env["GH_TOKEN"] = github_token
    completed = subprocess.run(
        ["gh", "repo", "clone", manifest.repository, str(destination)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    if completed.returncode != 0:
        raise RepoPrepError(
            f"clone failed for {manifest.repository}: {completed.stderr.strip()}"
        )
    _run_git(
        ["git", "checkout", "-B", manifest.task_branch, manifest.base_sha],
        cwd=destination,
        env=_scrub_token_env(env, github_token),
    )
    if manifest.patch and manifest.changed_files:
        patch_path = destination / ".gg-task.patch"
        patch_path.write_text(manifest.patch, encoding="utf-8")
        _run_git(
            ["git", "apply", str(patch_path)],
            cwd=destination,
            env=_scrub_token_env(env, github_token),
        )
        patch_path.unlink(missing_ok=True)


def _scrub_token_env(env: dict[str, str], token: str) -> dict[str, str]:
    scrubbed = dict(env)
    scrubbed.pop("GH_TOKEN", None)
    scrubbed.pop("GG_GITHUB_CLONE_TOKEN", None)
    if token:
        scrubbed["GIT_CONFIG_COUNT"] = "1"
        scrubbed["GIT_CONFIG_KEY_0"] = "http.extraHeader"
        scrubbed["GIT_CONFIG_VALUE_0"] = f"Authorization: Bearer {token}"
    return scrubbed


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
