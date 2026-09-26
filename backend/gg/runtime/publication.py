"""Deterministic draft-PR publication with a durable operation journal.

Commit and push the task branch, then create or recover exactly one draft
pull request. Bot credentials are process-scoped for git and header-only for
GitHub; they never appear in journal rows or public records.
"""

from __future__ import annotations

import os
import stat
import subprocess
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from gg.runtime.github import (
    GitHubError,
    GitHubGateway,
    GitHubTimeoutError,
    RemotePullRequest,
)
from gg.runtime.ledger import PublicationIdentityError, TaskLedger
from gg.sdk.publication import (
    PublicationRecord,
    PublicationRequest,
    PublicationState,
)
from gg.sdk.task_execution import AgentOutcome, CheckOutcome, CommandCapture


TASK_MARKER_PREFIX = "gg-task-marker:"


class PublicationError(RuntimeError):
    """Publication could not be completed."""


class PublicationConflictError(PublicationError):
    """Remote git or GitHub state conflicts with this task's intended identity."""


class PublicationUncertainError(PublicationError):
    """A GitHub side effect may have occurred; reconcile before retrying."""


@dataclass(frozen=True)
class BotIdentity:
    """Commit author used for platform-created commits."""

    name: str
    email: str
    login: str


class DraftPublisher:
    """Commit, push, and reconcile one draft PR per task."""

    def __init__(
        self,
        *,
        ledger: TaskLedger,
        github: GitHubGateway,
        bot: BotIdentity,
        github_token: str,
        process_env: Mapping[str, str] | None = None,
    ) -> None:
        if not github_token or github_token != github_token.strip():
            raise PublicationError("github token must be a non-empty secret")
        self._ledger = ledger
        self._github = github
        self._bot = bot
        self._github_token = github_token
        self._process_env = dict(process_env or os.environ)

    def __repr__(self) -> str:
        return f"DraftPublisher(bot={self._bot.login!r})"

    async def publish(
        self, request: PublicationRequest, *, repo_dir: Path | None = None
    ) -> PublicationRecord:
        existing = self._ledger.get_publication(request.task_id)
        if existing is not None:
            if existing.state is PublicationState.PUBLISHED:
                return existing
            if existing.state is PublicationState.SKIPPED:
                return existing
            if existing.state is PublicationState.FAILED and _is_conflict(
                existing.detail
            ):
                raise PublicationConflictError(
                    existing.detail or "publication conflict"
                )

        if not _should_publish(request):
            return self._record_skip(request, existing)

        adopted = await self.adopt_existing(request)
        if adopted is not None:
            return adopted

        if repo_dir is None:
            raise PublicationError("repo_dir is required to publish changes")
        self._assert_not_base_branch(request)
        commit_sha = self._commit_task_branch(request, repo_dir)
        record, _ = self._begin(request, commit_sha=commit_sha)
        if record.state is PublicationState.PUBLISHED:
            return record
        try:
            if record.state in {
                PublicationState.PENDING,
                PublicationState.FAILED,
            }:
                await self._push_branch(request, repo_dir, commit_sha)
                record = self._ledger.update_publication(
                    request.task_id, state=PublicationState.PUSHED
                )
            if record.state is PublicationState.PUSHED:
                record = self._ledger.update_publication(
                    request.task_id, state=PublicationState.CREATING
                )
            pr = await self._reconcile_or_create(request, commit_sha)
            return self._record_published(request, pr, commit_sha)
        except PublicationConflictError as exc:
            self._ledger.update_publication(
                request.task_id,
                state=PublicationState.FAILED,
                detail=f"conflict: {exc}",
            )
            raise
        except PublicationUncertainError as exc:
            self._ledger.update_publication(
                request.task_id,
                state=PublicationState.CREATING,
                detail=f"uncertain: {exc}",
            )
            raise
        except PublicationError:
            raise

    async def adopt_existing(
        self, request: PublicationRequest
    ) -> PublicationRecord | None:
        """Recover a sandbox-published PR without making a second commit."""

        if not _should_publish(request) or request.head_sha is None:
            return None
        self._assert_not_base_branch(request)
        try:
            remote_sha = await self._github.get_branch_sha(
                request.repository, request.task_branch
            )
        except GitHubError as exc:
            raise PublicationError(_redact(str(exc), self._github_token)) from exc
        if remote_sha != request.head_sha:
            return None
        matched = await self._matching_pull_requests(request)
        if len(matched) > 1:
            raise PublicationConflictError(
                "multiple pull requests match repository/head/base/task marker"
            )
        if not matched:
            return None
        pr = matched[0]
        if pr.state != "open" or pr.head_sha != request.head_sha:
            raise PublicationConflictError(
                "task pull request does not match the published branch head"
            )
        self._begin(request, commit_sha=request.head_sha)
        return self._record_published(request, pr, request.head_sha)

    def _record_skip(
        self,
        request: PublicationRequest,
        existing: PublicationRecord | None,
    ) -> PublicationRecord:
        if existing is not None and existing.pr_number is not None:
            return existing
        detail = _skip_detail(request)
        record, created = self._begin(
            request,
            commit_sha=None,
            state=PublicationState.SKIPPED,
            detail=detail,
        )
        if not created:
            if record.state is PublicationState.PUBLISHED:
                return record
            if record.state is not PublicationState.SKIPPED:
                return self._ledger.update_publication(
                    request.task_id,
                    state=PublicationState.SKIPPED,
                    detail=detail,
                    outcome_detail=detail,
                    check_status=request.check_outcome.value,
                )
            return record
        return self._ledger.update_publication(
            request.task_id,
            state=PublicationState.SKIPPED,
            detail=detail,
            outcome_detail=detail,
            check_status=request.check_outcome.value,
        )

    def _begin(
        self,
        request: PublicationRequest,
        *,
        commit_sha: str | None,
        state: PublicationState = PublicationState.PENDING,
        detail: str | None = None,
    ) -> tuple[PublicationRecord, bool]:
        try:
            return self._ledger.begin_publication(
                task_id=request.task_id,
                repository=request.repository,
                task_branch=request.task_branch,
                base_ref=request.base_ref,
                task_marker=request.task_marker,
                commit_sha=commit_sha,
                check_outcome=request.check_outcome,
                agent_outcome=request.agent_outcome,
                state=state,
                detail=detail,
            )
        except PublicationIdentityError as exc:
            raise PublicationConflictError(str(exc)) from exc

    def _assert_not_base_branch(self, request: PublicationRequest) -> None:
        if request.task_branch == request.base_ref:
            raise PublicationError("refusing to push to the base branch")
        if request.task_branch.startswith("-"):
            raise PublicationError("task branch must not look like a git flag")
        if ".." in request.task_branch:
            raise PublicationError("task branch must not contain '..'")

    def _commit_task_branch(self, request: PublicationRequest, repo_dir: Path) -> str:
        env = self._git_identity_env()
        branch = _run_git(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_dir,
            env=env,
            token=self._github_token,
        )
        if branch == request.base_ref:
            _run_git(
                ["git", "checkout", "-B", request.task_branch],
                cwd=repo_dir,
                env=env,
                token=self._github_token,
            )
        _run_git(
            ["git", "add", "-A"],
            cwd=repo_dir,
            env=env,
            token=self._github_token,
        )
        status = _run_git(
            ["git", "status", "--porcelain"],
            cwd=repo_dir,
            env=env,
            token=self._github_token,
        )
        if status:
            message = (
                f"gg-task {request.task_id}\n\n"
                f"{TASK_MARKER_PREFIX} {request.task_marker}\n"
            )
            _run_git(
                ["git", "-c", "commit.gpgsign=false", "commit", "-m", message],
                cwd=repo_dir,
                env=env,
                token=self._github_token,
            )
        sha = _run_git(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_dir,
            env=env,
            token=self._github_token,
        )
        if sha == request.base_sha:
            raise PublicationError("no commit to publish on the task branch")
        return sha

    async def _push_branch(
        self,
        request: PublicationRequest,
        repo_dir: Path,
        commit_sha: str,
    ) -> None:
        with _git_auth_env(self._process_env, self._github_token) as env:
            remote_sha = _ls_remote(
                repo_dir,
                request.task_branch,
                env=env,
                token=self._github_token,
            )
        try:
            api_sha = await self._github.get_branch_sha(
                request.repository, request.task_branch
            )
        except GitHubError as exc:
            raise PublicationError(_redact(str(exc), self._github_token)) from exc
        if remote_sha and api_sha and remote_sha != api_sha:
            raise PublicationConflictError(
                f"git remote SHA and GitHub API SHA disagree for {request.task_branch}"
            )
        existing = remote_sha or api_sha
        if existing and existing != commit_sha:
            raise PublicationConflictError(
                f"remote branch {request.task_branch} is at {existing}, "
                f"not intended commit {commit_sha}"
            )
        if existing == commit_sha:
            return
        with _git_auth_env(self._process_env, self._github_token) as env:
            env.update(_identity_env(self._bot))
            _run_git(
                [
                    "git",
                    "push",
                    "--",
                    "origin",
                    f"{commit_sha}:refs/heads/{request.task_branch}",
                ],
                cwd=repo_dir,
                env=env,
                token=self._github_token,
            )
        _assert_origin_has_no_secret(repo_dir, self._github_token)

    async def _reconcile_or_create(
        self, request: PublicationRequest, commit_sha: str
    ) -> RemotePullRequest:
        matched = await self._matching_pull_requests(request)
        if len(matched) == 1:
            return matched[0]
        if len(matched) > 1:
            raise PublicationConflictError(
                "multiple pull requests match repository/head/base/task marker"
            )
        others = await self._head_base_pull_requests(request)
        if others:
            raise PublicationConflictError(
                "remote pull request exists for this head/base without this task marker"
            )
        try:
            created = await self._github.create_draft_pull_request(
                request.repository,
                title=_pr_title(request),
                body=_pr_body(request, commit_sha),
                head=request.task_branch,
                base=request.base_ref,
            )
        except GitHubTimeoutError as exc:
            recovered = await self._matching_pull_requests(request)
            if len(recovered) == 1:
                return recovered[0]
            if len(recovered) > 1:
                raise PublicationConflictError(
                    "multiple pull requests match after a create timeout"
                ) from exc
            raise PublicationUncertainError(
                "create timed out and no matching pull request was found"
            ) from exc
        except GitHubError as exc:
            recovered = await self._matching_pull_requests(request)
            if len(recovered) == 1:
                return recovered[0]
            raise PublicationError(_redact(str(exc), self._github_token)) from exc
        if not created.draft:
            raise PublicationError("GitHub created a non-draft pull request")
        return created

    async def _matching_pull_requests(
        self, request: PublicationRequest
    ) -> tuple[RemotePullRequest, ...]:
        found = await self._head_base_pull_requests(request)
        marker = marker_token(request.task_marker)
        return tuple(pr for pr in found if marker in pr.body or marker in pr.title)

    async def _head_base_pull_requests(
        self, request: PublicationRequest
    ) -> tuple[RemotePullRequest, ...]:
        try:
            return await self._github.list_pull_requests(
                request.repository,
                head=request.task_branch,
                base=request.base_ref,
                state="all",
            )
        except GitHubTimeoutError as exc:
            raise PublicationUncertainError("listing pull requests timed out") from exc
        except GitHubError as exc:
            raise PublicationError(_redact(str(exc), self._github_token)) from exc

    def _record_published(
        self,
        request: PublicationRequest,
        pr: RemotePullRequest,
        commit_sha: str,
    ) -> PublicationRecord:
        outcome_detail = _published_outcome_detail(request)
        return self._ledger.update_publication(
            request.task_id,
            state=PublicationState.PUBLISHED,
            commit_sha=commit_sha,
            pr_number=pr.number,
            pr_url=pr.html_url,
            pr_draft=pr.draft,
            pr_author=pr.author,
            pr_state=pr.state,
            detail=outcome_detail,
            check_status=request.check_outcome.value,
            outcome_detail=outcome_detail,
        )

    def _git_identity_env(self) -> dict[str, str]:
        env = dict(self._process_env)
        env.update(_identity_env(self._bot))
        env.pop("GH_TOKEN", None)
        env.pop("GITHUB_TOKEN", None)
        env.pop("GG_GITHUB_CLONE_TOKEN", None)
        return env


def marker_token(task_marker: str) -> str:
    return f"{TASK_MARKER_PREFIX} {task_marker}"


def _should_publish(request: PublicationRequest) -> bool:
    return request.agent_outcome is AgentOutcome.SUCCEEDED and bool(
        request.changed_files
    )


def _skip_detail(request: PublicationRequest) -> str:
    if request.agent_outcome is AgentOutcome.NO_CHANGES:
        return "no_changes"
    if request.agent_outcome is AgentOutcome.CANCELLED:
        return "cancelled_without_publication"
    if request.agent_outcome in {
        AgentOutcome.FAILED,
        AgentOutcome.TIMEOUT,
        AgentOutcome.NOT_RUN,
    }:
        return "agent_failure_without_publication"
    return "no_changes"


def _published_outcome_detail(request: PublicationRequest) -> str:
    if request.check_outcome is CheckOutcome.FAILED:
        return "checks_failed"
    if request.check_outcome is CheckOutcome.TIMEOUT:
        return "checks_timed_out"
    if request.check_outcome is CheckOutcome.PASSED:
        return "checks_passed"
    return "published"


def _is_conflict(detail: str | None) -> bool:
    return bool(detail) and detail.startswith("conflict:")


def _pr_title(request: PublicationRequest) -> str:
    return f"gg-task {request.task_id}"


def _pr_body(request: PublicationRequest, commit_sha: str) -> str:
    check = request.check
    check_lines = _check_body(request.check_outcome, check)
    files = "\n".join(f"- `{name}`" for name in request.changed_files) or "- (none)"
    return (
        f"<!-- {marker_token(request.task_marker)} -->\n\n"
        f"# Task `{request.task_id}`\n\n"
        f"- Repository: `{request.repository}`\n"
        f"- Branch: `{request.task_branch}`\n"
        f"- Base: `{request.base_ref}` (`{request.base_sha}`)\n"
        f"- Head: `{commit_sha}`\n"
        f"- Agent outcome: `{request.agent_outcome.value}`\n"
        f"- Check outcome: `{request.check_outcome.value}`\n\n"
        f"{check_lines}\n\n"
        f"## Changed files\n\n{files}\n"
    )


def _check_body(outcome: CheckOutcome, capture: CommandCapture | None) -> str:
    heading = {
        CheckOutcome.PASSED: "## Measured checks: passed",
        CheckOutcome.FAILED: "## Measured checks: FAILED",
        CheckOutcome.TIMEOUT: "## Measured checks: timed out",
        CheckOutcome.NOT_RUN: "## Measured checks: not run",
    }[outcome]
    if capture is None:
        return heading
    output = (capture.stdout or "") + (capture.stderr or "")
    if capture.stdout_truncated or capture.stderr_truncated:
        output += "\n[truncated]"
    output = output.strip() or "(no output)"
    if len(output) > 4000:
        output = output[:4000] + "\n[truncated]"
    return (
        f"{heading}\n\n"
        f"- command: `{capture.command}`\n"
        f"- exit_code: `{capture.exit_code}`\n"
        f"- duration_ms: `{capture.duration_ms}`\n"
        f"- timed_out: `{capture.timed_out}`\n\n"
        f"```\n{output}\n```"
    )


def _identity_env(bot: BotIdentity) -> dict[str, str]:
    return {
        "GIT_AUTHOR_NAME": bot.name,
        "GIT_AUTHOR_EMAIL": bot.email,
        "GIT_COMMITTER_NAME": bot.name,
        "GIT_COMMITTER_EMAIL": bot.email,
    }


def _redact(text: str, token: str) -> str:
    return text.replace(token, "[REDACTED]") if token else text


def _run_git(
    args: list[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    token: str,
) -> str:
    if "--force" in args or "-f" in args:
        raise PublicationError("force-push is not allowed")
    completed = subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        env=dict(env),
        check=False,
    )
    if completed.returncode != 0:
        detail = _redact(
            (completed.stderr or completed.stdout or "git failed").strip(),
            token,
        )
        raise PublicationError(f"{args[0]} {args[1]} failed: {detail}")
    return completed.stdout.strip()


def _ls_remote(
    repo_dir: Path, branch: str, *, env: Mapping[str, str], token: str
) -> str | None:
    output = _run_git(
        ["git", "ls-remote", "--", "origin", f"refs/heads/{branch}"],
        cwd=repo_dir,
        env=env,
        token=token,
    )
    if not output:
        return None
    return output.split()[0]


def _assert_origin_has_no_secret(repo_dir: Path, token: str) -> None:
    completed = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    url = completed.stdout.strip()
    if token and token in url:
        raise PublicationError("origin URL contains a credential")
    if "@" in url and url.startswith("https://") and "github.com/" in url:
        public = "https://github.com/" + url.split("github.com/", 1)[1]
        subprocess.run(
            ["git", "remote", "set-url", "origin", public],
            cwd=repo_dir,
            check=False,
        )


@contextmanager
def _git_auth_env(
    process_env: Mapping[str, str], token: str
) -> Iterator[dict[str, str]]:
    with tempfile.TemporaryDirectory() as tmp:
        askpass = Path(tmp) / "askpass"
        askpass.write_text(
            "#!/bin/sh\n"
            'case "$1" in\n'
            "  *[Uu]sername*) echo x-access-token ;;\n"
            '  *) echo "$GG_GIT_ASKPASS_TOKEN" ;;\n'
            "esac\n",
            encoding="utf-8",
        )
        askpass.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        env = dict(process_env)
        env["GG_GIT_ASKPASS_TOKEN"] = token
        env["GIT_ASKPASS"] = str(askpass)
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["GIT_CONFIG_COUNT"] = "1"
        env["GIT_CONFIG_KEY_0"] = "credential.helper"
        env["GIT_CONFIG_VALUE_0"] = ""
        env.pop("GIT_CONFIG_PARAMETERS", None)
        yield env


__all__ = [
    "BotIdentity",
    "DraftPublisher",
    "PublicationConflictError",
    "PublicationError",
    "PublicationUncertainError",
    "TASK_MARKER_PREFIX",
    "marker_token",
]
