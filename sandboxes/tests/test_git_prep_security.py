"""Git clone keeps short-lived installation credentials out of public state."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from gg.server.task_supervisor.git_prep import GitPrepError, clone_repository


def test_clone_failure_does_not_publish_credential(monkeypatch, tmp_path: Path) -> None:
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 1, "", "secret-installation-token")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(GitPrepError) as error:
        clone_repository(
            repository="alice/private",
            destination=tmp_path / "repo",
            github_token="secret-installation-token",
            process_env={"GG_GITHUB_CLONE_TOKEN": "secret-installation-token"},
        )
    assert "secret-installation-token" not in str(error.value)
    args, options = calls[0]
    assert args == [
        "git",
        "clone",
        "--",
        "https://github.com/alice/private.git",
        str(tmp_path / "repo"),
    ]
    assert "secret-installation-token" not in " ".join(args)
    assert options["env"]["GIT_CONFIG_KEY_0"] == "http.https://github.com/.extraheader"
