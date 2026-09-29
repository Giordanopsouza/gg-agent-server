from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from gg.server.task_supervisor.pi_publication import (
    NoChanges,
    PublicationConflict,
    PublicationTimeout,
    RemotePull,
    marker_line,
    open_or_update_draft,
    publish_draft,
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
    intent_path: Path | None = None

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
        if self.intent_path is not None:
            saved = json.loads(self.intent_path.read_text(encoding="utf-8"))
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
    intent = tmp_path / "intent.json"
    intent.write_text(
        json.dumps(
            {
                "repository": "other/repo",
                "task_branch": "gg/task/task-1",
                "base_ref": "main",
                "task_marker": "task-1",
                "commit_sha": None,
            }
        ),
        encoding="utf-8",
    )
    github = FakeGitHub()
    with pytest.raises(PublicationConflict):
        publish_draft(
            repo_dir=tmp_path,
            repository="owner/repo",
            task_branch="gg/task/task-1",
            base_ref="main",
            task_marker="task-1",
            intent_path=intent,
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
            intent_path=tmp_path / "intent.json",
            client=github,
        )
    assert github.creates == 0


def test_commit_push_persists_intent_before_create(tmp_path: Path) -> None:
    work = _repo(tmp_path)
    (work / "README.md").write_text("changed\n", encoding="utf-8")
    intent = tmp_path / "intent.json"
    github = FakeGitHub(intent_path=intent)
    pull = publish_draft(
        repo_dir=work,
        repository="owner/repo",
        task_branch="gg/task/task-1",
        base_ref="main",
        task_marker="task-1",
        intent_path=intent,
        client=github,
        check_outcome="not_run",
    )
    assert pull is not None
    assert github.creates == 1
    assert "Check outcome: `not_run`" in pull.body
    assert marker_line("task-1") in pull.body
    saved = json.loads(intent.read_text(encoding="utf-8"))
    assert saved["commit_sha"] == pull.head_sha
    remote = _git(
        ["git", "ls-remote", str(tmp_path / "origin.git"), "refs/heads/gg/task/task-1"],
        tmp_path,
    )
    assert pull.head_sha in remote
