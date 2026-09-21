"""Clone and branch preparation without embedding credentials in URLs."""

from __future__ import annotations

import subprocess
from pathlib import Path

from gg.sdk.task_execution import CommandCapture
from gg.server.task_supervisor.commands import run_bounded_command


class GitPrepError(RuntimeError):
    """Repository preparation failed before agent work began."""


def resolve_base_sha(
    *,
    repo_dir: Path,
    base_ref: str,
) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", base_ref],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise GitPrepError(
            f"could not resolve base ref {base_ref!r}: {completed.stderr.strip()}"
        )
    return completed.stdout.strip()


def clone_repository(
    *,
    repository: str,
    destination: Path,
    github_token: str,
    process_env: dict[str, str],
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and any(destination.iterdir()):
        raise GitPrepError(f"destination {destination} is not empty")
    completed = subprocess.run(
        ["gh", "repo", "clone", repository, str(destination)],
        capture_output=True,
        text=True,
        env=_clone_env(process_env, github_token),
        check=False,
    )
    if completed.returncode != 0:
        raise GitPrepError(f"clone failed for {repository}: {completed.stderr.strip()}")
    _scrub_origin_credentials(destination)


def checkout_task_branch(*, repo_dir: Path, branch: str, base_sha: str) -> None:
    completed = subprocess.run(
        ["git", "checkout", "-B", branch, base_sha],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise GitPrepError(
            f"could not create branch {branch!r} at {base_sha}: "
            f"{completed.stderr.strip()}"
        )


def collect_git_evidence(
    *,
    repo_dir: Path,
    base_sha: str,
    max_patch_bytes: int,
) -> tuple[str | None, tuple[str, ...], str | None, bool]:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    if head.returncode != 0:
        raise GitPrepError(head.stderr.strip() or "git rev-parse HEAD failed")
    head_sha = head.stdout.strip()

    names = subprocess.run(
        ["git", "diff", "--name-only", base_sha],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    if names.returncode != 0:
        raise GitPrepError(names.stderr.strip() or "git diff --name-only failed")
    changed = tuple(line for line in names.stdout.splitlines() if line.strip())

    patch = subprocess.run(
        ["git", "diff", base_sha],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    if patch.returncode != 0:
        raise GitPrepError(patch.stderr.strip() or "git diff failed")
    patch_text = patch.stdout
    truncated = False
    encoded = patch_text.encode("utf-8", errors="replace")
    if len(encoded) > max_patch_bytes:
        patch_text = encoded[:max_patch_bytes].decode("utf-8", errors="ignore")
        truncated = True
    return head_sha, changed, patch_text, truncated


def run_bootstrap(
    *,
    repo_dir: Path,
    command: str,
    timeout_seconds: float,
    max_output_bytes: int,
    process_env: dict[str, str],
) -> CommandCapture:
    return run_bounded_command(
        command=command,
        cwd=str(repo_dir),
        timeout_seconds=timeout_seconds,
        max_output_bytes=max_output_bytes,
        process_env=process_env,
    )


def _clone_env(process_env: dict[str, str], token: str) -> dict[str, str]:
    env = dict(process_env)
    env["GH_TOKEN"] = token
    env.pop("GIT_ASKPASS", None)
    return env


def _scrub_origin_credentials(repo_dir: Path) -> None:
    completed = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return
    url = completed.stdout.strip()
    if "@" not in url:
        return
    # Replace tokenized HTTPS URLs with the public form.
    if url.startswith("https://") and "github.com/" in url:
        public = "https://github.com/" + url.split("github.com/", 1)[1]
        subprocess.run(
            ["git", "remote", "set-url", "origin", public],
            cwd=repo_dir,
            check=False,
        )


__all__ = [
    "GitPrepError",
    "checkout_task_branch",
    "clone_repository",
    "collect_git_evidence",
    "resolve_base_sha",
    "run_bootstrap",
]
