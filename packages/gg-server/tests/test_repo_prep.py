from __future__ import annotations

import os
import subprocess
from pathlib import Path

from gg.runtime.repo_prep import prepare_repo_from_manifest
from gg.sdk.task_execution import AgentOutcome, TaskResultManifest


def _git(*args: str, cwd: Path, env: dict[str, str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.rstrip("\n")


def test_prepare_repo_clones_and_applies_patch_without_gh(tmp_path: Path) -> None:
    env = os.environ.copy()
    env.update(
        GIT_AUTHOR_NAME="seed",
        GIT_AUTHOR_EMAIL="seed@example.com",
        GIT_COMMITTER_NAME="seed",
        GIT_COMMITTER_EMAIL="seed@example.com",
    )
    remote_root = tmp_path / "remote"
    remote_root.mkdir()
    origin = remote_root / "repo.git"
    _git("init", "--bare", "-b", "main", str(origin), cwd=tmp_path, env=env)
    seed = tmp_path / "seed"
    seed.mkdir()
    _git("init", "-b", "main", cwd=seed, env=env)
    (seed / "README.md").write_text("before\n", encoding="utf-8")
    _git("add", "README.md", cwd=seed, env=env)
    _git("-c", "commit.gpgsign=false", "commit", "-m", "seed", cwd=seed, env=env)
    base_sha = _git("rev-parse", "HEAD", cwd=seed, env=env)
    _git("remote", "add", "origin", str(origin), cwd=seed, env=env)
    _git("push", "origin", "main", cwd=seed, env=env)
    (seed / "README.md").write_text("after\n", encoding="utf-8")
    patch = _git("diff", cwd=seed, env=env) + "\n"

    # Route the GitHub URL to a local bare repository; no network or real token.
    git_config = tmp_path / "gitconfig"
    _git(
        "config",
        "--file",
        str(git_config),
        f"url.{remote_root}/.insteadOf",
        "https://github.com/owner/",
        cwd=tmp_path,
        env=env,
    )
    env["GIT_CONFIG_GLOBAL"] = str(git_config)
    env["GH_TOKEN"] = "dummy-token"
    env["GG_GITHUB_CLONE_TOKEN"] = "dummy-token"
    manifest = TaskResultManifest(
        task_id="task-1",
        execution_id="execution-1",
        repository="owner/repo",
        task_branch="gg/task/task-1",
        base_ref="main",
        base_sha=base_sha,
        changed_files=("README.md",),
        patch=patch,
        agent_outcome=AgentOutcome.SUCCEEDED,
    )
    destination = tmp_path / "prepared"

    prepare_repo_from_manifest(
        manifest,
        destination=destination,
        github_token="dummy-token",
        process_env=env,
    )

    assert (destination / "README.md").read_text(encoding="utf-8") == "after\n"
    assert _git("branch", "--show-current", cwd=destination, env=env) == (
        "gg/task/task-1"
    )
    assert _git("status", "--porcelain", cwd=destination, env=env) == (" M README.md")
    assert "dummy-token" not in (destination / ".git" / "config").read_text()
