from __future__ import annotations

import base64
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from gg.server.task_supervisor.pi_publication import (
    GhPullRequestClient,
    NoChanges,
    PublicationConflict,
    PublicationError,
    PublicationTimeout,
    RemotePull,
    _push,
    _write_intent,
    load_publication_intent,
    main,
    marker_line,
    open_or_update_draft,
    publish_draft,
    reported_check_outcome,
)


def _git(args: list[str], cwd: Path) -> str:
    completed = subprocess.run(
        args, cwd=cwd, capture_output=True, text=True, check=True
    )
    return completed.stdout.strip()


def _repo(tmp_path: Path) -> Path:
    origin = tmp_path / "origin.git"
    origin.mkdir()
    subprocess.run(["git", "init", "--bare", "-b", "main"], cwd=origin, check=True)
    seed = tmp_path / "seed"
    seed.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=seed, check=True)
    (seed / "README.md").write_text("seed\n", encoding="utf-8")
    _git(["git", "add", "README.md"], seed)
    _git(
        [
            "git",
            "-c",
            "user.name=seed",
            "-c",
            "user.email=seed@example.com",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-m",
            "seed",
        ],
        seed,
    )
    _git(["git", "remote", "add", "origin", str(origin)], seed)
    _git(["git", "push", "-u", "origin", "main"], seed)
    work = tmp_path / "work"
    subprocess.run(["git", "clone", str(origin), str(work)], check=True)
    subprocess.run(["git", "checkout", "-B", "gg/task/task-1"], cwd=work, check=True)
    return work


@dataclass
class FakeGitHub:
    pulls: list[RemotePull] = field(default_factory=list)
    creates: int = 0
    lose_create: bool = False
    state_db: Path | None = None

    def list_pull_requests(
        self, repository: str, *, head: str, base: str
    ) -> tuple[RemotePull, ...]:
        del repository
        return tuple(
            pull
            for pull in self.pulls
            if pull.head_ref == head and pull.base_ref == base
        )

    def create_draft(
        self,
        repository: str,
        *,
        title: str,
        body: str,
        head: str,
        base: str,
    ) -> RemotePull:
        if self.state_db is not None:
            saved = load_publication_intent(self.state_db, "task-1")
            assert saved["commit_sha"]
            head_sha = str(saved["commit_sha"])
        else:
            head_sha = "abc123"
        self.creates += 1
        pull = RemotePull(
            number=7,
            html_url=f"https://github.com/{repository}/pull/7",
            draft=True,
            state="open",
            title=title,
            body=body,
            head_ref=head,
            base_ref=base,
            head_sha=head_sha,
        )
        self.pulls.append(pull)
        if self.lose_create:
            raise PublicationTimeout("create response lost")
        return pull

    def update_pull(
        self, repository: str, number: int, *, title: str, body: str
    ) -> RemotePull:
        del repository
        current = next(pull for pull in self.pulls if pull.number == number)
        updated = RemotePull(
            number=current.number,
            html_url=current.html_url,
            draft=True,
            state="open",
            title=title,
            body=body,
            head_ref=current.head_ref,
            base_ref=current.base_ref,
            head_sha=current.head_sha,
        )
        self.pulls = [updated if pull.number == number else pull for pull in self.pulls]
        return updated


def test_timeout_after_create_reuses_the_same_draft(tmp_path: Path) -> None:
    github = FakeGitHub(lose_create=True)
    first = open_or_update_draft(
        repository="owner/repo",
        task_branch="gg/task/task-1",
        base_ref="main",
        task_marker="task-1",
        head_sha="abc123",
        title="gg-task task-1",
        body=f"<!-- {marker_line('task-1')} -->\n",
        client=github,
    )
    github.lose_create = False
    second = open_or_update_draft(
        repository="owner/repo",
        task_branch="gg/task/task-1",
        base_ref="main",
        task_marker="task-1",
        head_sha="abc123",
        title="gg-task task-1",
        body=f"<!-- {marker_line('task-1')} -->\n",
        client=github,
    )
    assert first.number == second.number == 7
    assert github.creates == 1


def test_identity_conflict_does_not_create(tmp_path: Path) -> None:
    intent = tmp_path / "sandbox.db"
    _write_intent(
        intent,
        repository="other/repo",
        task_branch="gg/task/task-1",
        base_ref="main",
        task_marker="task-1",
        commit_sha=None,
        check_outcome="not_run",
    )
    github = FakeGitHub()
    with pytest.raises(PublicationConflict):
        publish_draft(
            repo_dir=tmp_path,
            repository="owner/repo",
            task_branch="gg/task/task-1",
            base_ref="main",
            task_marker="task-1",
            state_db=intent,
            client=github,
        )
    assert github.creates == 0


def test_no_changes_does_not_create_a_pull_request(tmp_path: Path) -> None:
    work = _repo(tmp_path)
    github = FakeGitHub()
    with pytest.raises(NoChanges):
        publish_draft(
            repo_dir=work,
            repository="owner/repo",
            task_branch="gg/task/task-1",
            base_ref="main",
            task_marker="task-1",
            state_db=tmp_path / "sandbox.db",
            client=github,
        )
    assert github.creates == 0


def test_commit_push_persists_intent_before_create(tmp_path: Path) -> None:
    work = _repo(tmp_path)
    (work / "README.md").write_text("changed\n", encoding="utf-8")
    intent = tmp_path / "sandbox.db"
    github = FakeGitHub(state_db=intent)
    pull = publish_draft(
        repo_dir=work,
        repository="owner/repo",
        task_branch="gg/task/task-1",
        base_ref="main",
        task_marker="task-1",
        state_db=intent,
        client=github,
        check_outcome="passed",
    )
    assert pull is not None
    assert github.creates == 1
    assert "Check outcome: `passed`" in pull.body
    assert marker_line("task-1") in pull.body
    saved = load_publication_intent(intent, "task-1")
    assert saved["commit_sha"] == pull.head_sha
    assert (
        reported_check_outcome(
            intent,
            repository="owner/repo",
            task_branch="gg/task/task-1",
            base_ref="main",
            task_marker="task-1",
        )
        == "passed"
    )
    remote = _git(
        ["git", "ls-remote", str(tmp_path / "origin.git"), "refs/heads/gg/task/task-1"],
        tmp_path,
    )
    assert pull.head_sha in remote


def test_push_uses_task_token_only_for_the_git_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[list[str], dict[str, str]]] = []

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((args, kwargs["env"]))  # type: ignore[arg-type]
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    original = {"GH_TOKEN": "task-token", "PATH": "/usr/bin"}
    _push(tmp_path, "gg/task/task-1", "abc123", original)

    args, env = calls[0]
    assert args == ["git", "push", "--", "origin", "abc123:refs/heads/gg/task/task-1"]
    assert env["GIT_CONFIG_KEY_0"] == "http.https://github.com/.extraheader"
    assert env["GIT_CONFIG_VALUE_0"] == (
        "Authorization: Basic "
        + base64.b64encode(b"x-access-token:task-token").decode()
    )
    assert original == {"GH_TOKEN": "task-token", "PATH": "/usr/bin"}


def test_push_does_not_echo_the_token_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 1, "", "task-token")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(PublicationError, match="git push failed") as exc:
        _push(tmp_path, "gg/task/task-1", "abc123", {"GH_TOKEN": "task-token"})
    assert "task-token" not in str(exc.value)


def test_gh_create_and_edit_view_the_pull_after_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = GhPullRequestClient()
    calls: list[list[str]] = []
    row = {
        "number": 7,
        "url": "https://github.com/owner/repo/pull/7",
        "isDraft": True,
        "state": "OPEN",
        "title": "gg-task task-1",
        "body": "gg-task-marker: task-1",
        "headRefName": "gg/task/task-1",
        "baseRefName": "main",
        "headRefOid": "abc123",
    }

    def fake_gh(args: list[str]) -> str:
        calls.append(args)
        if args[:2] == ["pr", "create"]:
            assert "--json" not in args
            return row["url"] + "\n"
        if args[:2] == ["pr", "edit"]:
            assert "--json" not in args
            return ""
        assert args[:2] == ["pr", "view"]
        return json.dumps(row)

    monkeypatch.setattr(client, "_gh", fake_gh)
    created = client.create_draft(
        "owner/repo",
        title="gg-task task-1",
        body="gg-task-marker: task-1",
        head="gg/task/task-1",
        base="main",
    )
    updated = client.update_pull(
        "owner/repo", 7, title="gg-task task-1", body="gg-task-marker: task-1"
    )
    assert created == updated
    assert [args[:2] for args in calls] == [
        ["pr", "create"],
        ["pr", "view"],
        ["pr", "edit"],
        ["pr", "view"],
    ]


def test_cli_passes_the_task_environment_to_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    def fake_publish(**kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setenv("GH_TOKEN", "task-token")
    monkeypatch.setattr(
        "gg.server.task_supervisor.pi_publication.publish_draft", fake_publish
    )
    assert (
        main(
            [
                "--repository",
                "owner/repo",
                "--branch",
                "gg/task/task-1",
                "--base",
                "main",
                "--marker",
                "task-1",
                "--state-db",
                str(tmp_path / "sandbox.db"),
                "--check-outcome",
                "failed",
            ]
        )
        == 0
    )
    assert captured["process_env"]["GH_TOKEN"] == "task-token"
    assert captured["check_outcome"] == "failed"


def test_publish_restart_after_lost_create_keeps_one_pr(tmp_path: Path) -> None:
    work = _repo(tmp_path)
    (work / "README.md").write_text("changed\n")
    db = tmp_path / "sandbox.db"
    github = FakeGitHub(state_db=db, lose_create=True)
    arguments = dict(
        repo_dir=work,
        repository="owner/repo",
        task_branch="gg/task/task-1",
        base_ref="main",
        task_marker="task-1",
        state_db=db,
        client=github,
    )
    first = publish_draft(**arguments)
    github.lose_create = False
    second = publish_draft(**arguments)
    assert first.number == second.number
    assert github.creates == 1
    assert load_publication_intent(db, "task-1")["commit_sha"] == first.head_sha
    assert not list(tmp_path.glob("*.json"))


def test_standalone_cli_reopens_sqlite_and_reuses_one_local_pr(tmp_path):
    """Real helper subprocesses + Git; gh is a local fixture, no external calls."""
    import os
    import sqlite3
    import sys

    work = _repo(tmp_path)
    (work / "README.md").write_text("CLI change\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    state_db = tmp_path / "state with spaces.db"
    remote_db = tmp_path / "fake-remote.db"
    gh = bin_dir / "gh"
    gh.write_text(
        f"#!{sys.executable}\n"
        + r"""
import json, os, sqlite3, sys
from pathlib import Path
from gg.server.task_supervisor.pi_publication import load_publication_intent
args = sys.argv[1:]
with sqlite3.connect(os.environ["FAKE_REMOTE_DB"]) as db:
    db.execute("CREATE TABLE IF NOT EXISTS pulls "
               "(number INTEGER PRIMARY KEY, payload TEXT)")
    rows = db.execute("SELECT payload FROM pulls").fetchall()
    if args[:2] == ["pr", "list"]:
        print(json.dumps([json.loads(row[0]) for row in rows]))
    elif args[:2] == ["pr", "create"]:
        assert not rows, "a second PR was attempted"
        intent = load_publication_intent(Path(os.environ["FAKE_STATE_DB"]), "task-1")
        row = dict(number=7, url="https://github.com/owner/repo/pull/7", isDraft=True,
                   state="OPEN", title="gg-task task-1", body="gg-task-marker: task-1",
                   headRefName=intent["task_branch"], baseRefName=intent["base_ref"],
                   headRefOid=intent["commit_sha"])
        db.execute("INSERT INTO pulls VALUES (7, ?)", (json.dumps(row),))
        print(row["url"])
    elif args[:2] == ["pr", "edit"]:
        assert len(rows) == 1
    elif args[:2] == ["pr", "view"]:
        print(rows[0][0])
    else:
        raise RuntimeError("unexpected gh command")
"""
    )
    gh.chmod(0o755)
    env = dict(
        os.environ,
        PATH=str(bin_dir) + os.pathsep + os.environ["PATH"],
        FAKE_REMOTE_DB=str(remote_db),
        FAKE_STATE_DB=str(state_db),
        GH_TOKEN="test-fixture-token",
    )
    command = [
        sys.executable,
        "-m",
        "gg.server.task_supervisor.pi_publication",
        "--repository",
        "owner/repo",
        "--branch",
        "gg/task/task-1",
        "--base",
        "main",
        "--marker",
        "task-1",
        "--state-db",
        str(state_db),
        "--check-outcome",
        "passed",
        "--repo-dir",
        str(work),
    ]
    for _ in range(2):
        subprocess.run(
            command, env=env, cwd=work, check=True, capture_output=True, text=True
        )
    with sqlite3.connect(remote_db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM pulls").fetchone()[0] == 1
    intent = load_publication_intent(state_db, "task-1")
    assert intent["check_outcome"] == "passed"
    assert intent["commit_sha"] in _git(
        ["git", "ls-remote", str(tmp_path / "origin.git"), "refs/heads/gg/task/task-1"],
        tmp_path,
    )
