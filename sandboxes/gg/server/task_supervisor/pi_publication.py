"""Commit, push, and open or update one draft pull request from Pi's environment.

The task installation token is already in ``GH_TOKEN`` for the Pi process.
The CLI passes its inherited environment to Git so the task token can
authenticate one push. ``gh`` inherits that same token for GitHub API calls.

A prompt can tell Pi not to merge. That is not a permission boundary: the
installation token can write, and a write token can merge unless repository
protections forbid it. This command never calls a merge API.
"""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from gg.server.config import publication_process_env


MARKER_PREFIX = "gg-task-marker:"


class PublicationError(RuntimeError):
    """Pi could not publish the task branch."""


class PublicationConflict(PublicationError):
    """Remote state does not match this task's persisted identity."""


class PublicationTimeout(PublicationError):
    """A GitHub response was lost after a side effect may have happened."""


class NoChanges(PublicationError):
    """The worktree has nothing to publish."""


@dataclass(frozen=True)
class RemotePull:
    """Credential-free pull request returned by GitHub."""

    number: int
    html_url: str
    draft: bool
    state: str
    title: str
    body: str
    head_ref: str
    base_ref: str
    head_sha: str


class PullRequestClient(Protocol):
    def list_pull_requests(
        self, repository: str, *, head: str, base: str
    ) -> tuple[RemotePull, ...]: ...

    def create_draft(
        self,
        repository: str,
        *,
        title: str,
        body: str,
        head: str,
        base: str,
    ) -> RemotePull: ...

    def update_pull(
        self, repository: str, number: int, *, title: str, body: str
    ) -> RemotePull: ...


def marker_line(task_marker: str) -> str:
    return f"{MARKER_PREFIX} {task_marker}"


def publication_instructions(
    *,
    repository: str,
    task_branch: str,
    base_ref: str,
    task_marker: str,
    intent_path: Path,
) -> str:
    """Tell Pi how to publish without treating that text as a merge lock."""

    command = (
        "python -m gg.server.task_supervisor.pi_publication "
        f"--repository {repository} --branch {task_branch} --base {base_ref} "
        f"--marker {task_marker} --intent-path {intent_path}"
    )
    return (
        "After you edit the repository and run the tests you can, commit on "
        f"branch `{task_branch}`, push it, and create or update one draft pull "
        f"request into `{base_ref}` for `{repository}`. The persistent task "
        f"marker is `{marker_line(task_marker)}`. Look up an existing pull "
        "request for this head, base, and marker before creating one, and look "
        "again if the create response is lost. Do not open a second pull "
        "request and do not merge.\n\n"
        "Run this command from the repository. It commits, pushes, and "
        "creates or updates the draft:\n\n"
        f"`{command}`\n\n"
        "Use only the GH_TOKEN already in this environment. Do not copy in "
        "another GitHub token. Add `--check-outcome passed` to the command "
        "if all checks you ran passed, or `--check-outcome failed` if any "
        "failed. Omit it when no checks ran. Report the checks in your final "
        "message. A finished conversation "
        "is not evidence that CI passed.\n\n"
        "Draft pull requests are merged manually on GitHub. Telling you not to "
        "merge does not technically prevent a merge: this token can write, and "
        "a write token can merge when the repository allows it. Do not run "
        "`gh pr merge` or the merge API."
    )


def publish_draft(
    *,
    repo_dir: Path,
    repository: str,
    task_branch: str,
    base_ref: str,
    task_marker: str,
    intent_path: Path,
    client: PullRequestClient,
    process_env: Mapping[str, str] | None = None,
    check_outcome: str = "not_run",
) -> RemotePull | None:
    """Persist identity, then commit, push, and create or update one draft."""

    if task_branch == base_ref or task_branch.startswith("-") or ".." in task_branch:
        raise PublicationError("refusing to publish this branch")
    if check_outcome not in {"passed", "failed", "not_run"}:
        raise PublicationError("invalid check outcome")
    _assert_identity(intent_path, repository, task_branch, base_ref, task_marker)
    _write_intent(
        intent_path,
        repository=repository,
        task_branch=task_branch,
        base_ref=base_ref,
        task_marker=task_marker,
        commit_sha=None,
        check_outcome=check_outcome,
    )
    env = None if process_env is None else dict(process_env)
    _commit_if_needed(repo_dir, task_marker, env)
    head = _git(repo_dir, ["rev-parse", "HEAD"], env)
    base = _git(repo_dir, ["rev-parse", f"origin/{base_ref}"], env)
    status = _git(repo_dir, ["status", "--porcelain"], env)
    if head == base and not status:
        raise NoChanges("no_changes")
    _write_intent(
        intent_path,
        repository=repository,
        task_branch=task_branch,
        base_ref=base_ref,
        task_marker=task_marker,
        commit_sha=head,
        check_outcome=check_outcome,
    )
    _push(repo_dir, task_branch, head, env)
    return open_or_update_draft(
        repository=repository,
        task_branch=task_branch,
        base_ref=base_ref,
        task_marker=task_marker,
        head_sha=head,
        title=f"gg-task {task_marker}",
        body=_body(task_marker, head, check_outcome),
        client=client,
    )


def open_or_update_draft(
    *,
    repository: str,
    task_branch: str,
    base_ref: str,
    task_marker: str,
    head_sha: str,
    title: str,
    body: str,
    client: PullRequestClient,
) -> RemotePull:
    """Create or update one draft. A lost create is reconciled by listing."""

    matched = _matching(client, repository, task_branch, base_ref, task_marker)
    if len(matched) > 1:
        raise PublicationConflict(
            "multiple pull requests match repository/head/base/task marker"
        )
    if len(matched) == 1:
        current = matched[0]
        _require_same_pull(current, task_branch, base_ref, head_sha)
        updated = client.update_pull(repository, current.number, title=title, body=body)
        _require_same_pull(updated, task_branch, base_ref, head_sha)
        return updated
    others = client.list_pull_requests(repository, head=task_branch, base=base_ref)
    if others:
        raise PublicationConflict(
            "remote pull request exists for this head/base without this task marker"
        )
    try:
        created = client.create_draft(
            repository, title=title, body=body, head=task_branch, base=base_ref
        )
    except PublicationTimeout:
        recovered = _matching(client, repository, task_branch, base_ref, task_marker)
        if len(recovered) == 1:
            _require_same_pull(recovered[0], task_branch, base_ref, head_sha)
            return recovered[0]
        if len(recovered) > 1:
            raise PublicationConflict(
                "multiple pull requests match after a create timeout"
            ) from None
        raise
    if not created.draft:
        raise PublicationError("GitHub created a non-draft pull request")
    _require_same_pull(created, task_branch, base_ref, head_sha)
    return created


def _matching(
    client: PullRequestClient,
    repository: str,
    task_branch: str,
    base_ref: str,
    task_marker: str,
) -> tuple[RemotePull, ...]:
    found = client.list_pull_requests(repository, head=task_branch, base=base_ref)
    marker = marker_line(task_marker)
    return tuple(pr for pr in found if marker in pr.body or marker in pr.title)


def _require_same_pull(
    pull: RemotePull, task_branch: str, base_ref: str, head_sha: str
) -> None:
    if pull.head_ref != task_branch or pull.base_ref != base_ref:
        raise PublicationConflict("pull request head or base does not match")
    if pull.head_sha != head_sha:
        raise PublicationConflict("pull request head sha does not match")
    if not pull.draft or pull.state != "open":
        raise PublicationConflict("task pull request is not an open draft")


def _body(task_marker: str, head_sha: str, check_outcome: str) -> str:
    return (
        f"<!-- {marker_line(task_marker)} -->\n\n"
        f"- Head: `{head_sha}`\n"
        f"- Check outcome: `{check_outcome}`\n\n"
        "Draft pull request. Merge manually on GitHub.\n"
        "A prompt not to merge does not remove write permission from the token.\n"
    )


def _assert_identity(
    path: Path,
    repository: str,
    task_branch: str,
    base_ref: str,
    task_marker: str,
) -> None:
    if not path.is_file():
        return
    saved = json.loads(path.read_text(encoding="utf-8"))
    if (
        saved.get("repository") != repository
        or saved.get("task_branch") != task_branch
        or saved.get("base_ref") != base_ref
        or saved.get("task_marker") != task_marker
    ):
        raise PublicationConflict("existing publication identity does not match task")


def reported_check_outcome(
    path: Path,
    *,
    repository: str,
    task_branch: str,
    base_ref: str,
    task_marker: str,
) -> str:
    """Read the check result Pi supplied to its publication command."""

    if not path.is_file():
        return "not_run"
    _assert_identity(path, repository, task_branch, base_ref, task_marker)
    saved = json.loads(path.read_text(encoding="utf-8"))
    outcome = saved.get("check_outcome", "not_run")
    if outcome not in {"passed", "failed", "not_run"}:
        raise PublicationConflict("invalid publication check outcome")
    return outcome


def _write_intent(
    path: Path,
    *,
    repository: str,
    task_branch: str,
    base_ref: str,
    task_marker: str,
    commit_sha: str | None,
    check_outcome: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and commit_sha is None:
        saved = json.loads(path.read_text(encoding="utf-8"))
        commit_sha = saved.get("commit_sha")
    payload = {
        "repository": repository,
        "task_branch": task_branch,
        "base_ref": base_ref,
        "task_marker": task_marker,
        "commit_sha": commit_sha,
        "check_outcome": check_outcome,
    }
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload), encoding="utf-8")
    temporary.replace(path)


def _commit_if_needed(
    repo_dir: Path, task_marker: str, env: dict[str, str] | None
) -> None:
    status = _git(repo_dir, ["status", "--porcelain"], env)
    if not status:
        return
    _git(repo_dir, ["add", "-A"], env)
    _git(
        repo_dir,
        [
            "-c",
            "user.name=gg-task",
            "-c",
            "user.email=gg-task@users.noreply.github.com",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-m",
            f"gg-task {task_marker}\n\n{marker_line(task_marker)}\n",
        ],
        env,
    )


def _push(repo_dir: Path, branch: str, head: str, env: dict[str, str] | None) -> None:
    push_env = None if env is None else dict(env)
    if push_env is not None and (token := push_env.get("GH_TOKEN")):
        credential = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        push_env["GIT_CONFIG_COUNT"] = "1"
        push_env["GIT_CONFIG_KEY_0"] = "http.https://github.com/.extraheader"
        push_env["GIT_CONFIG_VALUE_0"] = f"Authorization: Basic {credential}"
        push_env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        _git(
            repo_dir,
            ["push", "--", "origin", f"{head}:refs/heads/{branch}"],
            push_env,
        )
    except PublicationError:
        # Git diagnostics can include request headers; keep the token out of logs.
        raise PublicationError("git push failed") from None


def _git(repo_dir: Path, args: list[str], env: dict[str, str] | None) -> str:
    if "--force" in args or "-f" in args:
        raise PublicationError("force-push is not allowed")
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "git failed").strip()
        raise PublicationError(f"git {' '.join(args)} failed: {detail}")
    return completed.stdout.strip()


class GhPullRequestClient:
    """`gh` adapter. The token stays in the inherited process environment."""

    def __init__(self, *, timeout_seconds: float = 30.0) -> None:
        self._timeout = timeout_seconds

    def list_pull_requests(
        self, repository: str, *, head: str, base: str
    ) -> tuple[RemotePull, ...]:
        owner, _name = _owner_repo(repository)
        payload = self._gh(
            [
                "pr",
                "list",
                "--repo",
                repository,
                "--head",
                f"{owner}:{head}",
                "--base",
                base,
                "--state",
                "all",
                "--json",
                "number,url,isDraft,state,title,body,headRefName,baseRefName,headRefOid",
            ]
        )
        rows = json.loads(payload or "[]")
        return tuple(_pull_from_gh(row) for row in rows)

    def create_draft(
        self,
        repository: str,
        *,
        title: str,
        body: str,
        head: str,
        base: str,
    ) -> RemotePull:
        url = self._gh(
            [
                "pr",
                "create",
                "--repo",
                repository,
                "--draft",
                "--title",
                title,
                "--body",
                body,
                "--head",
                head,
                "--base",
                base,
            ]
        ).strip()
        prefix = f"https://github.com/{repository}/pull/"
        if not url.startswith(prefix) or not url[len(prefix) :].isdigit():
            raise PublicationError("gh pr create returned an invalid pull request URL")
        return self._view_pull(repository, url)

    def update_pull(
        self, repository: str, number: int, *, title: str, body: str
    ) -> RemotePull:
        self._gh(
            [
                "pr",
                "edit",
                str(number),
                "--repo",
                repository,
                "--title",
                title,
                "--body",
                body,
            ]
        )
        return self._view_pull(repository, str(number))

    def _view_pull(self, repository: str, number_or_url: str) -> RemotePull:
        payload = self._gh(
            [
                "pr",
                "view",
                number_or_url,
                "--repo",
                repository,
                "--json",
                "number,url,isDraft,state,title,body,headRefName,baseRefName,headRefOid",
            ]
        )
        return _pull_from_gh(json.loads(payload))

    def _gh(self, args: list[str]) -> str:
        try:
            completed = subprocess.run(
                ["gh", *args],
                capture_output=True,
                text=True,
                timeout=self._timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise PublicationTimeout("gh timed out") from exc
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "gh failed").strip()
            raise PublicationError(f"gh {' '.join(args[:2])} failed: {detail}")
        return completed.stdout


def _owner_repo(repository: str) -> tuple[str, str]:
    owner, separator, name = repository.partition("/")
    if not separator or not owner or not name or "/" in name:
        raise PublicationError(f"repository must be 'owner/name', got {repository!r}")
    return owner, name


def _pull_from_gh(row: dict[str, object]) -> RemotePull:
    state = str(row.get("state") or "open").lower()
    return RemotePull(
        number=int(row["number"]),
        html_url=str(row.get("url") or ""),
        draft=bool(row.get("isDraft")),
        state=state,
        title=str(row.get("title") or ""),
        body=str(row.get("body") or ""),
        head_ref=str(row.get("headRefName") or ""),
        base_ref=str(row.get("baseRefName") or ""),
        head_sha=str(row.get("headRefOid") or ""),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Publish one draft pull request")
    parser.add_argument("--repository", required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--marker", required=True)
    parser.add_argument("--intent-path", required=True, type=Path)
    parser.add_argument(
        "--check-outcome", choices=("passed", "failed", "not_run"), default="not_run"
    )
    parser.add_argument("--repo-dir", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    try:
        publish_draft(
            repo_dir=args.repo_dir,
            repository=args.repository,
            task_branch=args.branch,
            base_ref=args.base,
            task_marker=args.marker,
            intent_path=args.intent_path,
            client=GhPullRequestClient(),
            process_env=publication_process_env(),
            check_outcome=args.check_outcome,
        )
    except NoChanges:
        print("no_changes")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
