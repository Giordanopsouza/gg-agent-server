from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from uuid import UUID

import pytest

from gg.runtime.github import GitHubTimeoutError, RemotePullRequest
from gg.runtime.ledger import TaskResultArchive
from gg.runtime.publication import (
    BotIdentity,
    DraftPublisher,
    PublicationConflictError,
    PublicationError,
    PublicationUncertainError,
    marker_token,
)
from gg.runtime.task_supervision import manager as manager_module
from gg.runtime.task_supervision.manager import TaskSupervisionManager
from gg.sdk.publication import PublicationRequest, PublicationState
from gg.sdk.task_execution import AgentOutcome, CheckOutcome, TaskResultManifest
from test_support.postgres_ledger import new_ledger


TOKEN = "task-installation-token"
OWNER = UUID("00000000-0000-0000-0000-00000000000a")
BOT = BotIdentity(name="gg-bot", email="gg-bot@users.noreply.github.com", login="app")


def _request(
    task_id: str,
    *,
    agent_outcome: AgentOutcome = AgentOutcome.SUCCEEDED,
    check_outcome: CheckOutcome = CheckOutcome.NOT_RUN,
    changed_files: tuple[str, ...] = ("README.md",),
    head_sha: str | None = "abc123",
    repository: str = "owner/repo",
) -> PublicationRequest:
    return PublicationRequest(
        task_id=task_id,
        repository=repository,
        task_branch=f"gg/task/{task_id}",
        base_ref="main",
        base_sha="base123",
        head_sha=head_sha,
        task_marker=task_id,
        agent_outcome=agent_outcome,
        check_outcome=check_outcome,
        changed_files=changed_files,
    )


def _pull(
    repository: str,
    request: PublicationRequest,
    *,
    url: str | None = None,
    body: str | None = None,
    number: int = 7,
) -> RemotePullRequest:
    return RemotePullRequest(
        number=number,
        html_url=url or f"https://github.com/{repository}/pull/{number}",
        draft=True,
        state="open",
        author="app",
        title="gg-task",
        body=body
        if body is not None
        else f"<!-- {marker_token(request.task_marker)} -->",
        head_ref=request.task_branch,
        base_ref=request.base_ref,
        head_sha=request.head_sha or "abc123",
    )


@dataclass
class FakeGitHub:
    pulls: list[RemotePullRequest] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    timeouts_remaining: int = 0

    async def get_authenticated_login(self) -> str:
        return "app"

    async def get_branch_sha(self, repository: str, branch: str) -> str | None:
        del repository, branch
        return None

    async def list_pull_requests(
        self, repository: str, *, head: str, base: str, state: str = "all"
    ) -> tuple[RemotePullRequest, ...]:
        del repository, state
        self.calls.append("list_pull_requests")
        if self.timeouts_remaining:
            self.timeouts_remaining -= 1
            raise GitHubTimeoutError("list timed out")
        return tuple(
            pull
            for pull in self.pulls
            if pull.head_ref == head and pull.base_ref == base
        )

    async def create_draft_pull_request(
        self, *args: object, **kwargs: object
    ) -> object:
        self.calls.append("create_draft_pull_request")
        raise AssertionError("host must not create a pull request")


def _publisher(ledger, github: FakeGitHub) -> DraftPublisher:
    return DraftPublisher(
        ledger=ledger,
        github=github,
        bot=BOT,
        github_token=TOKEN,
    )


@pytest.mark.anyio
async def test_timeout_then_restart_adopts_one_pull_request_without_creating() -> None:
    ledger = new_ledger()
    ledger.open()
    record, _ = ledger.submit(
        idempotency_key="pi-timeout",
        repository="owner/repo",
        prompt="edit",
        base_ref="main",
        retry_of=None,
        owner_id=OWNER,
    )
    request = _request(record.id)
    github = FakeGitHub(timeouts_remaining=1)
    publisher = _publisher(ledger, github)
    with pytest.raises(PublicationUncertainError):
        await publisher.reconcile_observed(request)
    github.pulls.append(_pull("owner/repo", request))
    published = await publisher.reconcile_observed(request)
    assert published.state is PublicationState.PUBLISHED
    assert published.pr_url == "https://github.com/owner/repo/pull/7"
    assert published.check_outcome is CheckOutcome.NOT_RUN
    assert published.detail == "checks_not_run"
    assert "create_draft_pull_request" not in github.calls
    ledger.close()


@pytest.mark.anyio
async def test_identity_conflict_does_not_create_another_pull_request() -> None:
    ledger = new_ledger()
    ledger.open()
    record, _ = ledger.submit(
        idempotency_key="pi-conflict",
        repository="owner/repo",
        prompt="edit",
        base_ref="main",
        retry_of=None,
        owner_id=OWNER,
    )
    ledger.begin_publication(
        task_id=record.id,
        repository="other/repo",
        task_branch=f"gg/task/{record.id}",
        base_ref="main",
        task_marker=record.id,
        commit_sha=None,
        check_outcome=CheckOutcome.NOT_RUN,
        agent_outcome=AgentOutcome.NOT_RUN,
    )
    github = FakeGitHub()
    with pytest.raises(PublicationConflictError):
        await _publisher(ledger, github).reconcile_observed(_request(record.id))
    assert github.calls == []
    ledger.close()


@pytest.mark.anyio
async def test_no_changes_skips_publication() -> None:
    ledger = new_ledger()
    ledger.open()
    record, _ = ledger.submit(
        idempotency_key="pi-none",
        repository="owner/repo",
        prompt="look only",
        base_ref="main",
        retry_of=None,
        owner_id=OWNER,
    )
    github = FakeGitHub()
    skipped = await _publisher(ledger, github).reconcile_observed(
        _request(
            record.id,
            agent_outcome=AgentOutcome.NO_CHANGES,
            changed_files=(),
            head_sha=None,
        )
    )
    assert skipped.state is PublicationState.SKIPPED
    assert skipped.detail == "no_changes"
    assert "create_draft_pull_request" not in github.calls
    ledger.close()


@pytest.mark.anyio
async def test_cancel_after_publication_keeps_the_pull_request() -> None:
    ledger = new_ledger()
    ledger.open()
    record, _ = ledger.submit(
        idempotency_key="pi-cancel",
        repository="owner/repo",
        prompt="edit",
        base_ref="main",
        retry_of=None,
        owner_id=OWNER,
    )
    request = _request(record.id, agent_outcome=AgentOutcome.CANCELLED)
    github = FakeGitHub(pulls=[_pull("owner/repo", request)])
    published = await _publisher(ledger, github).reconcile_observed(request)
    assert published.state is PublicationState.PUBLISHED
    assert published.pr_number == 7
    again = await _publisher(ledger, github).reconcile_observed(request)
    assert again.pr_number == 7
    assert "create_draft_pull_request" not in github.calls
    ledger.close()


@pytest.mark.anyio
async def test_chat_url_is_not_accepted_as_publication_proof() -> None:
    ledger = new_ledger()
    ledger.open()
    record, _ = ledger.submit(
        idempotency_key="pi-url",
        repository="owner/repo",
        prompt="edit",
        base_ref="main",
        retry_of=None,
        owner_id=OWNER,
    )
    request = _request(record.id)
    github = FakeGitHub(
        pulls=[
            _pull(
                "owner/repo",
                request,
                url="https://evil.example/pull/7",
                body=(
                    f"see https://github.com/owner/repo/pull/7\n"
                    f"<!-- {marker_token(record.id)} -->"
                ),
            )
        ]
    )
    with pytest.raises(PublicationConflictError, match="URL"):
        await _publisher(ledger, github).reconcile_observed(request)
    assert ledger.get_publication(record.id) is None or (
        ledger.get_publication(record.id).state is not PublicationState.PUBLISHED
    )
    assert "create_draft_pull_request" not in github.calls
    ledger.close()


@pytest.mark.anyio
async def test_missing_pull_request_is_explicit_and_not_created_by_the_host() -> None:
    ledger = new_ledger()
    ledger.open()
    record, _ = ledger.submit(
        idempotency_key="pi-missing",
        repository="owner/repo",
        prompt="edit",
        base_ref="main",
        retry_of=None,
        owner_id=OWNER,
    )
    github = FakeGitHub()
    with pytest.raises(PublicationError, match="pull_request_missing"):
        await _publisher(ledger, github).reconcile_observed(_request(record.id))
    saved = ledger.get_publication(record.id)
    assert saved is not None
    assert saved.detail == "pull_request_missing"
    assert saved.pr_url is None
    assert "create_draft_pull_request" not in github.calls
    ledger.close()


@pytest.mark.anyio
async def test_not_run_checks_are_not_reported_as_passed() -> None:
    ledger = new_ledger()
    ledger.open()
    record, _ = ledger.submit(
        idempotency_key="pi-checks",
        repository="owner/repo",
        prompt="edit",
        base_ref="main",
        retry_of=None,
        owner_id=OWNER,
    )
    request = _request(record.id, check_outcome=CheckOutcome.NOT_RUN)
    github = FakeGitHub(pulls=[_pull("owner/repo", request)])
    published = await _publisher(ledger, github).reconcile_observed(request)
    assert published.check_outcome is CheckOutcome.NOT_RUN
    assert published.detail == "checks_not_run"
    assert published.detail != "checks_passed"
    ledger.close()


class _RecordingPublisher:
    calls: list[str] = []
    tokens: list[str] = []

    def __init__(self, *, github_token: str, **kwargs: object) -> None:
        del kwargs
        self.tokens.append(github_token)

    async def reconcile_observed(self, request: PublicationRequest) -> None:
        del request
        self.calls.append("reconcile")

    async def publish(
        self, request: PublicationRequest, *, repo_dir: object = None
    ) -> None:
        del request, repo_dir
        self.calls.append("publish")

    async def adopt_existing(self, request: PublicationRequest) -> None:
        del request
        self.calls.append("adopt")


@pytest.mark.anyio
async def test_owner_finalization_reconciles_with_the_task_token(monkeypatch) -> None:
    _RecordingPublisher.calls = []
    _RecordingPublisher.tokens = []
    monkeypatch.setattr(manager_module, "DraftPublisher", _RecordingPublisher)
    ledger = new_ledger()
    ledger.open()
    record, _ = ledger.submit(
        idempotency_key="pi-owner",
        repository="alice/private",
        prompt="edit",
        base_ref="main",
        retry_of=None,
        owner_id=OWNER,
    )
    ledger.record_base_sha(record.id, "base123")

    class Authorization:
        def credential(self, owner_id, repository, base_ref):
            assert (owner_id, repository, base_ref) == (OWNER, "alice/private", "main")
            return SimpleNamespace(token="installation-token", base_sha="base123")

    supervision = TaskSupervisionManager(
        ledger=ledger,
        lifecycle=SimpleNamespace(),
        settings=SimpleNamespace(github_clone_token="global-token"),
        publisher=None,
        repository_authorization=Authorization(),
    )
    manifest = TaskResultManifest(
        task_id=record.id,
        execution_id="exec-1",
        repository="alice/private",
        task_branch=f"gg/task/{record.id}",
        base_ref="main",
        base_sha="base123",
        head_sha="abc123",
        changed_files=("README.md",),
        check_outcome=CheckOutcome.NOT_RUN,
        agent_outcome=AgentOutcome.SUCCEEDED,
    )
    archive = TaskResultArchive(
        task_id=record.id,
        execution_id="exec-1",
        manifest=manifest,
        evidence_complete=True,
        evidence_detail=None,
        archived_at=None,
    )
    await supervision._maybe_publish(record.id, manifest, archive)
    assert _RecordingPublisher.calls == ["reconcile"]
    assert _RecordingPublisher.tokens == ["installation-token"]
    ledger.close()
