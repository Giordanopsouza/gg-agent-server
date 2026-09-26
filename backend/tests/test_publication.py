from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import pytest

from gg.runtime.github import (
    GitHubTimeoutError,
    HttpGitHubGateway,
    RemotePullRequest,
)
from gg.runtime.ledger import TaskLedger
from gg.runtime.publication import (
    BotIdentity,
    DraftPublisher,
    PublicationConflictError,
    PublicationError,
    marker_token,
)
from gg.sdk.publication import PublicationRequest, PublicationState
from gg.sdk.task_execution import AgentOutcome, CheckOutcome, CommandCapture


TOKEN = "super-secret-github-token-do-not-leak"
BOT = BotIdentity(
    name="gg-bot", email="gg-bot@users.noreply.github.com", login="gg-bot"
)


def _git_env() -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": "seed",
            "GIT_AUTHOR_EMAIL": "seed@example.com",
            "GIT_COMMITTER_NAME": "seed",
            "GIT_COMMITTER_EMAIL": "seed@example.com",
        }
    )
    return env


def _run(args: list[str], *, cwd: Path) -> str:
    completed = subprocess.run(
        args, cwd=cwd, capture_output=True, text=True, check=True, env=_git_env()
    )
    return completed.stdout.strip()


def _prepared_repo(tmp_path: Path) -> tuple[Path, Path, str]:
    origin = tmp_path / "origin.git"
    origin.mkdir()
    subprocess.run(["git", "init", "--bare", "-b", "main"], cwd=origin, check=True)
    seed = tmp_path / "seed"
    seed.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=seed, check=True)
    (seed / "README.md").write_text("seed\n", encoding="utf-8")
    _run(["git", "add", "README.md"], cwd=seed)
    _run(["git", "-c", "commit.gpgsign=false", "commit", "-m", "seed"], cwd=seed)
    _run(["git", "remote", "add", "origin", str(origin)], cwd=seed)
    _run(["git", "push", "-u", "origin", "main"], cwd=seed)
    base_sha = _run(["git", "rev-parse", "HEAD"], cwd=seed)
    work = tmp_path / "work"
    subprocess.run(["git", "clone", str(origin), str(work)], check=True, env=_git_env())
    return work, origin, base_sha


def _edit(work: Path, branch: str) -> None:
    _run(["git", "checkout", "-B", branch], cwd=work)
    (work / "README.md").write_text("changed by task\n", encoding="utf-8")


def _ledger_with_task(repository: str = "owner/repo") -> tuple[TaskLedger, str]:
    ledger = TaskLedger(db_path=":memory:")
    ledger.open()
    record, _ = ledger.submit(
        idempotency_key="pub-1",
        repository=repository,
        prompt="edit readme",
        base_ref="main",
        retry_of=None,
    )
    return ledger, record.id


def _request(
    task_id: str,
    *,
    agent_outcome: AgentOutcome = AgentOutcome.SUCCEEDED,
    check_outcome: CheckOutcome = CheckOutcome.PASSED,
    changed_files: tuple[str, ...] = ("README.md",),
    branch: str | None = None,
    check: CommandCapture | None = None,
) -> PublicationRequest:
    return PublicationRequest(
        task_id=task_id,
        repository="owner/repo",
        task_branch=branch or f"gg/task/{task_id}",
        base_ref="main",
        base_sha="pending",
        task_marker=f"task:{task_id}",
        agent_outcome=agent_outcome,
        check_outcome=check_outcome,
        check=check,
        changed_files=changed_files,
    )


@dataclass
class FakeGitHub:
    ledger: TaskLedger
    task_id: str
    login: str = "gg-bot"
    pulls: list[RemotePullRequest] = field(default_factory=list)
    branch_shas: dict[str, str] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)
    create_calls: int = 0
    timeout_after_create: bool = False
    create_bodies: list[dict[str, str]] = field(default_factory=list)

    async def get_authenticated_login(self) -> str:
        self.calls.append("get_authenticated_login")
        return self.login

    async def get_branch_sha(self, repository: str, branch: str) -> str | None:
        self.calls.append("get_branch_sha")
        return self.branch_shas.get(f"{repository}:{branch}")

    async def list_pull_requests(
        self,
        repository: str,
        *,
        head: str,
        base: str,
        state: str = "all",
    ) -> tuple[RemotePullRequest, ...]:
        del repository
        self.calls.append("list_pull_requests")
        assert state == "all"
        return tuple(
            pr for pr in self.pulls if pr.head_ref == head and pr.base_ref == base
        )

    async def create_draft_pull_request(
        self,
        repository: str,
        *,
        title: str,
        body: str,
        head: str,
        base: str,
    ) -> RemotePullRequest:
        self.calls.append("create_draft_pull_request")
        intent = self.ledger.get_publication(self.task_id)
        assert intent is not None
        assert intent.commit_sha
        assert intent.repository == repository
        assert intent.task_branch == head
        assert intent.base_ref == base
        assert intent.task_marker
        self.create_calls += 1
        self.create_bodies.append(
            {"title": title, "body": body, "head": head, "base": base}
        )
        pr = RemotePullRequest(
            number=100 + len(self.pulls),
            html_url=f"https://github.com/{repository}/pull/{100 + len(self.pulls)}",
            draft=True,
            state="open",
            author=self.login,
            title=title,
            body=body,
            head_ref=head,
            base_ref=base,
            head_sha=intent.commit_sha,
        )
        self.pulls.append(pr)
        if self.timeout_after_create:
            raise GitHubTimeoutError("create response lost")
        return pr


def _publisher(ledger: TaskLedger, github: FakeGitHub) -> DraftPublisher:
    return DraftPublisher(
        ledger=ledger,
        github=github,
        bot=BOT,
        github_token=TOKEN,
        process_env=os.environ,
    )


@pytest.mark.anyio
async def test_intent_is_persisted_before_push_when_origin_is_missing(
    tmp_path: Path,
) -> None:
    work, _origin, base_sha = _prepared_repo(tmp_path)
    ledger, task_id = _ledger_with_task()
    request = _request(task_id)
    request = request.model_copy(update={"base_sha": base_sha})
    _edit(work, request.task_branch)
    _run(["git", "remote", "remove", "origin"], cwd=work)
    github = FakeGitHub(ledger=ledger, task_id=task_id)
    publisher = _publisher(ledger, github)

    with pytest.raises(PublicationError):
        await publisher.publish(request, repo_dir=work)

    record = ledger.get_publication(task_id)
    assert record is not None
    assert record.commit_sha
    assert record.pr_number is None
    assert github.create_calls == 0
    assert TOKEN not in json.dumps(record.model_dump(mode="json"))


@pytest.mark.anyio
async def test_publish_creates_one_draft_pr_and_is_idempotent(tmp_path: Path) -> None:
    work, origin, base_sha = _prepared_repo(tmp_path)
    ledger, task_id = _ledger_with_task()
    request = _request(task_id, check_outcome=CheckOutcome.NOT_RUN).model_copy(
        update={"base_sha": base_sha}
    )
    _edit(work, request.task_branch)
    github = FakeGitHub(ledger=ledger, task_id=task_id)
    publisher = _publisher(ledger, github)

    first = await publisher.publish(request, repo_dir=work)
    assert first.pr_draft is True
    assert first.check_outcome is CheckOutcome.NOT_RUN
    restarted = DraftPublisher(
        ledger=ledger,
        github=github,
        bot=BOT,
        github_token=TOKEN,
        process_env=os.environ,
    )
    second = await restarted.publish(request, repo_dir=work)

    assert first.state is PublicationState.PUBLISHED
    assert first.pr_draft is True
    assert first.pr_author == "gg-bot"
    assert first.pr_number == second.pr_number
    assert github.create_calls == 1
    assert marker_token(request.task_marker) in github.create_bodies[0]["body"]
    remote_sha = _run(
        ["git", "ls-remote", str(origin), f"refs/heads/{request.task_branch}"],
        cwd=work,
    ).split()[0]
    assert remote_sha == first.commit_sha
    assert TOKEN not in str(first.model_dump())
    origin_url = _run(["git", "remote", "get-url", "origin"], cwd=work)
    assert TOKEN not in origin_url
    assert "merge" not in github.calls
    assert "ready_for_review" not in github.calls


@pytest.mark.anyio
async def test_adopts_sandbox_published_pr_without_creating_commit(
    tmp_path: Path,
) -> None:
    work, _origin, base_sha = _prepared_repo(tmp_path)
    ledger, task_id = _ledger_with_task()
    request = _request(task_id).model_copy(update={"base_sha": base_sha})
    _edit(work, request.task_branch)
    _run(["git", "add", "README.md"], cwd=work)
    _run(["git", "commit", "-m", "sandbox change"], cwd=work)
    head_sha = _run(["git", "rev-parse", "HEAD"], cwd=work)
    _run(["git", "push", "-u", "origin", request.task_branch], cwd=work)
    request = request.model_copy(update={"head_sha": head_sha})
    github = FakeGitHub(ledger=ledger, task_id=task_id)
    github.branch_shas[f"{request.repository}:{request.task_branch}"] = head_sha
    github.pulls.append(
        RemotePullRequest(
            number=32,
            html_url="https://github.com/owner/repo/pull/32",
            draft=True,
            state="open",
            author="gg-bot",
            title="sandbox PR",
            body=f"<!-- {marker_token(request.task_marker)} -->",
            head_ref=request.task_branch,
            base_ref=request.base_ref,
            head_sha=head_sha,
        )
    )

    record = await _publisher(ledger, github).publish(request)

    assert record.state is PublicationState.PUBLISHED
    assert record.commit_sha == head_sha
    assert record.pr_number == 32
    assert github.create_calls == 0
    assert "create_draft_pull_request" not in github.calls


@pytest.mark.anyio
async def test_timeout_after_create_is_reconciled_without_second_pr(
    tmp_path: Path,
) -> None:
    work, _origin, base_sha = _prepared_repo(tmp_path)
    ledger, task_id = _ledger_with_task()
    request = _request(task_id).model_copy(update={"base_sha": base_sha})
    _edit(work, request.task_branch)
    github = FakeGitHub(ledger=ledger, task_id=task_id, timeout_after_create=True)
    publisher = _publisher(ledger, github)

    recovered = await publisher.publish(request, repo_dir=work)
    github.timeout_after_create = False
    replay = await publisher.publish(request, repo_dir=work)

    assert recovered.pr_number == replay.pr_number
    assert github.create_calls == 1
    assert recovered.state is PublicationState.PUBLISHED
    assert recovered.pr_draft is True


@pytest.mark.anyio
async def test_existing_closed_pr_is_recovered_instead_of_creating(
    tmp_path: Path,
) -> None:
    work, _origin, base_sha = _prepared_repo(tmp_path)
    ledger, task_id = _ledger_with_task()
    request = _request(task_id).model_copy(update={"base_sha": base_sha})
    _edit(work, request.task_branch)
    github = FakeGitHub(ledger=ledger, task_id=task_id)
    github.pulls.append(
        RemotePullRequest(
            number=7,
            html_url="https://github.com/owner/repo/pull/7",
            draft=True,
            state="closed",
            author="gg-bot",
            title=f"gg-task {task_id}",
            body=f"<!-- {marker_token(request.task_marker)} -->\nclosed",
            head_ref=request.task_branch,
            base_ref="main",
            head_sha="already-there",
        )
    )
    publisher = _publisher(ledger, github)

    record = await publisher.publish(request, repo_dir=work)

    assert record.pr_number == 7
    assert record.pr_state == "closed"
    assert github.create_calls == 0


@pytest.mark.anyio
async def test_remote_branch_conflict_fails_without_force_push(
    tmp_path: Path,
) -> None:
    work, origin, base_sha = _prepared_repo(tmp_path)
    ledger, task_id = _ledger_with_task()
    request = _request(task_id).model_copy(update={"base_sha": base_sha})
    other = tmp_path / "other"
    subprocess.run(
        ["git", "clone", str(origin), str(other)], check=True, env=_git_env()
    )
    _run(["git", "checkout", "-B", request.task_branch], cwd=other)
    (other / "README.md").write_text("foreign change\n", encoding="utf-8")
    _run(["git", "add", "README.md"], cwd=other)
    _run(["git", "-c", "commit.gpgsign=false", "commit", "-m", "foreign"], cwd=other)
    _run(["git", "push", "-u", "origin", request.task_branch], cwd=other)
    foreign_sha = _run(["git", "rev-parse", "HEAD"], cwd=other)

    _edit(work, request.task_branch)
    github = FakeGitHub(ledger=ledger, task_id=task_id)
    publisher = _publisher(ledger, github)

    with pytest.raises(PublicationConflictError, match="remote branch"):
        await publisher.publish(request, repo_dir=work)

    still_remote = _run(
        ["git", "ls-remote", str(origin), f"refs/heads/{request.task_branch}"],
        cwd=work,
    ).split()[0]
    assert still_remote == foreign_sha
    assert github.create_calls == 0
    failed = ledger.get_publication(task_id)
    assert failed is not None
    assert failed.state is PublicationState.FAILED
    assert failed.detail is not None
    assert failed.detail.startswith("conflict:")


@pytest.mark.anyio
async def test_failed_checks_still_publish_draft_and_fail_the_task(
    tmp_path: Path,
) -> None:
    work, _origin, base_sha = _prepared_repo(tmp_path)
    ledger, task_id = _ledger_with_task()
    check = CommandCapture(
        command="make test",
        exit_code=1,
        duration_ms=12,
        stdout="1 failed",
        stderr="",
    )
    request = _request(
        task_id,
        check_outcome=CheckOutcome.FAILED,
        check=check,
    ).model_copy(update={"base_sha": base_sha})
    _edit(work, request.task_branch)
    github = FakeGitHub(ledger=ledger, task_id=task_id)
    publisher = _publisher(ledger, github)

    record = await publisher.publish(request, repo_dir=work)
    task = ledger.get(task_id)

    assert record.state is PublicationState.PUBLISHED
    assert record.pr_draft is True
    assert record.check_outcome is CheckOutcome.FAILED
    assert "FAILED" in github.create_bodies[0]["body"]
    assert "make test" in github.create_bodies[0]["body"]
    assert task is not None
    assert task.check_status == "failed"
    assert task.outcome_detail == "checks_failed"


@pytest.mark.anyio
async def test_no_changes_and_agent_failure_do_not_create_a_pr(
    tmp_path: Path,
) -> None:
    work, _origin, base_sha = _prepared_repo(tmp_path)
    ledger, task_id = _ledger_with_task()
    github = FakeGitHub(ledger=ledger, task_id=task_id)
    publisher = _publisher(ledger, github)

    skipped = await publisher.publish(
        _request(
            task_id,
            agent_outcome=AgentOutcome.NO_CHANGES,
            check_outcome=CheckOutcome.NOT_RUN,
            changed_files=(),
        ).model_copy(update={"base_sha": base_sha}),
        repo_dir=work,
    )
    assert skipped.state is PublicationState.SKIPPED
    assert skipped.pr_number is None
    assert skipped.detail == "no_changes"

    ledger2, failed_id = _ledger_with_task()
    github2 = FakeGitHub(ledger=ledger2, task_id=failed_id)
    failed = await _publisher(ledger2, github2).publish(
        _request(
            failed_id,
            agent_outcome=AgentOutcome.FAILED,
            check_outcome=CheckOutcome.NOT_RUN,
            changed_files=(),
        ).model_copy(update={"base_sha": base_sha}),
        repo_dir=work,
    )
    assert failed.state is PublicationState.SKIPPED
    assert failed.detail == "agent_failure_without_publication"
    assert github.create_calls == 0
    assert github2.create_calls == 0


@pytest.mark.anyio
async def test_existing_pr_is_kept_on_cancellation(tmp_path: Path) -> None:
    work, _origin, base_sha = _prepared_repo(tmp_path)
    ledger, task_id = _ledger_with_task()
    request = _request(task_id).model_copy(update={"base_sha": base_sha})
    _edit(work, request.task_branch)
    github = FakeGitHub(ledger=ledger, task_id=task_id)
    publisher = _publisher(ledger, github)
    published = await publisher.publish(request, repo_dir=work)

    cancelled = await publisher.publish(
        request.model_copy(update={"agent_outcome": AgentOutcome.CANCELLED}),
        repo_dir=work,
    )

    assert cancelled.pr_number == published.pr_number
    assert cancelled.pr_url == published.pr_url
    assert github.create_calls == 1


@pytest.mark.anyio
async def test_refuses_to_push_to_the_base_branch(tmp_path: Path) -> None:
    work, _origin, base_sha = _prepared_repo(tmp_path)
    ledger, task_id = _ledger_with_task()
    request = _request(task_id, branch="main").model_copy(update={"base_sha": base_sha})
    (work / "README.md").write_text("changed by task\n", encoding="utf-8")
    github = FakeGitHub(ledger=ledger, task_id=task_id)
    publisher = _publisher(ledger, github)

    with pytest.raises(PublicationError, match="base branch"):
        await publisher.publish(request, repo_dir=work)
    assert github.create_calls == 0


@pytest.mark.anyio
async def test_conflicting_head_base_pr_without_marker_fails(
    tmp_path: Path,
) -> None:
    work, _origin, base_sha = _prepared_repo(tmp_path)
    ledger, task_id = _ledger_with_task()
    request = _request(task_id).model_copy(update={"base_sha": base_sha})
    _edit(work, request.task_branch)
    github = FakeGitHub(ledger=ledger, task_id=task_id)
    github.pulls.append(
        RemotePullRequest(
            number=9,
            html_url="https://github.com/owner/repo/pull/9",
            draft=True,
            state="open",
            author="someone-else",
            title="manual pr",
            body="not our marker",
            head_ref=request.task_branch,
            base_ref="main",
            head_sha="other",
        )
    )
    publisher = _publisher(ledger, github)

    with pytest.raises(PublicationConflictError, match="without this task marker"):
        await publisher.publish(request, repo_dir=work)
    assert github.create_calls == 0


@pytest.mark.anyio
async def test_http_gateway_creates_drafts_and_redacts_tokens() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("Authorization")
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(
            201,
            json={
                "number": 3,
                "html_url": "https://github.com/owner/repo/pull/3",
                "draft": True,
                "state": "open",
                "title": "gg-task t",
                "body": "body",
                "user": {"login": "gg-bot"},
                "head": {"ref": "gg/task/t", "sha": "abc"},
                "base": {"ref": "main"},
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        gateway = HttpGitHubGateway(
            TOKEN, api_url="https://api.github.com", client=client
        )
        pr = await gateway.create_draft_pull_request(
            "owner/repo",
            title="gg-task t",
            body="body",
            head="gg/task/t",
            base="main",
        )

    assert pr.draft is True
    assert captured["body"] == {
        "title": "gg-task t",
        "body": "body",
        "head": "gg/task/t",
        "base": "main",
        "draft": True,
    }
    assert captured["authorization"] == f"Bearer {TOKEN}"
    assert TOKEN not in str(captured["url"])
    assert TOKEN not in repr(gateway)


@pytest.mark.github
@pytest.mark.anyio
async def test_live_draft_pr_has_bot_authorship(tmp_path: Path) -> None:
    if os.getenv("GG_RUN_GITHUB_TESTS") != "1":
        pytest.skip(
            "set GG_RUN_GITHUB_TESTS=1 to run the live GitHub publication smoke"
        )
    token = os.getenv("GG_GITHUB_CLONE_TOKEN") or os.getenv("GH_TOKEN")
    repository = os.getenv("GG_GITHUB_LIVE_REPO")
    if not token or not repository:
        pytest.skip("GG_GITHUB_CLONE_TOKEN and GG_GITHUB_LIVE_REPO are required")

    gateway = HttpGitHubGateway(token)
    login = await gateway.get_authenticated_login()
    work = tmp_path / "live"
    clone_env = os.environ.copy()
    clone_env["GH_TOKEN"] = token
    subprocess.run(
        ["gh", "repo", "clone", repository, str(work)],
        check=True,
        env=clone_env,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "remote", "set-url", "origin", f"https://github.com/{repository}.git"],
        cwd=work,
        check=True,
    )
    base_sha = _run(["git", "rev-parse", "HEAD"], cwd=work)
    ledger, task_id = _ledger_with_task(repository=repository)
    branch = f"gg/task/{task_id[:8]}-live"
    request = PublicationRequest(
        task_id=task_id,
        repository=repository,
        task_branch=branch,
        base_ref=_run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=work),
        base_sha=base_sha,
        task_marker=f"task:{task_id}",
        agent_outcome=AgentOutcome.SUCCEEDED,
        check_outcome=CheckOutcome.PASSED,
        check=CommandCapture(
            command="true",
            exit_code=0,
            duration_ms=1,
            stdout="ok",
            stderr="",
        ),
        changed_files=("README.md",),
    )
    readme = work / "README.md"
    previous = readme.read_text(encoding="utf-8") if readme.exists() else ""
    readme.write_text(previous + f"\nlive {task_id}\n", encoding="utf-8")
    publisher = DraftPublisher(
        ledger=ledger,
        github=gateway,
        bot=BotIdentity(
            name=login, email=f"{login}@users.noreply.github.com", login=login
        ),
        github_token=token,
        process_env=os.environ,
    )

    record = await publisher.publish(request, repo_dir=work)

    assert record.pr_draft is True
    assert record.pr_author == login
    assert record.pr_url
    assert token not in json.dumps(record.model_dump(mode="json"))
    origin_url = _run(["git", "remote", "get-url", "origin"], cwd=work)
    assert token not in origin_url
