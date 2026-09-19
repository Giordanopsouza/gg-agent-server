"""Docker Pi demo: three sandboxes each open a website PR.

The launcher starts three isolated agent-server containers at once. Each one
forwards the host OpenRouter key and GitHub token by name only, clones
``Giordanopsouza/personal-website``, and runs one Pi conversation::

    title       — change the site title
    background  — change the page background color
    font        — change the primary font

No host directory is mounted. Each sandbox proves its work with ``gh pr list``
before the context stops every container.

Run it after building the image::

    docker build -t gg-agent-server:dev .
    set -a && source .env && set +a
    uv run --no-editable python -m gg.sdk.demo.docker_pi_github_pr
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from collections import Counter
from collections.abc import Callable, Sequence
from contextlib import ExitStack
from dataclasses import dataclass
from uuid import uuid4

from gg.sdk import (
    ConversationStatus,
    DockerWorkspace,
    Event,
    EventKind,
    PiAgentConfig,
    RemoteConversation,
)


DEFAULT_IMAGE = "gg-agent-server:dev"
DEFAULT_WORKING_DIR = "/workspace/project"
DEFAULT_REPO = "Giordanopsouza/personal-website"
OPENROUTER_SECRET_NAME = "OPENROUTER_API_KEY"
GITHUB_SECRET_NAME = "GH_TOKEN"
SECRET_ENV_NAMES = (OPENROUTER_SECRET_NAME, GITHUB_SECRET_NAME)
PI_AGENT = PiAgentConfig(
    kind="pi",
    provider="openrouter",
    model="google/gemini-3.7-flash",
)
REQUIRED_EVENT_KINDS = frozenset(
    {
        EventKind.MESSAGE,
        EventKind.ACTION,
        EventKind.OBSERVATION,
        EventKind.STATUS,
    }
)


@dataclass(frozen=True)
class WebsiteTask:
    """One product change owned by a single sandbox."""

    slug: str
    instruction: str


WEBSITE_TASKS: tuple[WebsiteTask, ...] = (
    WebsiteTask(
        slug="title",
        instruction=(
            "Change the website title (document title and main heading) to a "
            "new, clearly different title. Do not change colors or fonts."
        ),
    ),
    WebsiteTask(
        slug="background",
        instruction=(
            "Change the page background color to a clearly different color. "
            "Do not change the title or fonts."
        ),
    ),
    WebsiteTask(
        slug="font",
        instruction=(
            "Change the primary font family to a clearly different font. "
            "Do not change the title or background color."
        ),
    ),
)

PullRequestLister = Callable[[str], str]
WorkspaceFactory = Callable[..., DockerWorkspace]


@dataclass(frozen=True)
class DockerPiGitHubTaskResult:
    """Evidence from one sandbox, captured before teardown."""

    slug: str
    container_id: str
    conversation_id: str
    conversation_status: ConversationStatus
    repo: str
    pull_requests: str
    marker: str
    events_url: str
    events: list[Event]


def run_demo(
    *,
    repo: str = DEFAULT_REPO,
    image: str = DEFAULT_IMAGE,
    working_dir: str = DEFAULT_WORKING_DIR,
    marker: str | None = None,
    workspace_factory: WorkspaceFactory = DockerWorkspace,
    pull_request_lister: PullRequestLister | None = None,
    pause: bool = False,
) -> tuple[DockerPiGitHubTaskResult, ...]:
    """Run three Pi sandboxes, prove each PR, and always stop the containers."""
    target_repo = _require_repo(repo)
    _require_secrets()
    run_id = marker if marker is not None else uuid4().hex
    lister = pull_request_lister or _read_open_pull_requests
    results: list[DockerPiGitHubTaskResult] = []

    with ExitStack() as stack:
        sessions: list[tuple[WebsiteTask, DockerWorkspace, RemoteConversation]] = []
        for _task in WEBSITE_TASKS:
            workspace = stack.enter_context(
                workspace_factory(
                    image=image,
                    working_dir=working_dir,
                    secret_env_names=list(SECRET_ENV_NAMES),
                    timeout=float(PI_AGENT.timeout_seconds),
                )
            )
            conversation = RemoteConversation(workspace=workspace, agent=PI_AGENT)
            sessions.append((_task, workspace, conversation))

        for task, workspace, conversation in sessions:
            task_marker = f"{run_id}-{task.slug}"
            conversation.send_message(
                _prompt(
                    working_dir=working_dir,
                    repo=target_repo,
                    task=task,
                    marker=task_marker,
                    run_id=run_id,
                )
            )
            conversation.run()
            if conversation.status != ConversationStatus.FINISHED:
                raise RuntimeError(
                    "Pi conversation did not finish successfully "
                    f"(slug={task.slug} status={conversation.status})"
                )

            container_id = workspace.container_id
            if container_id is None:
                raise RuntimeError(
                    "DockerWorkspace did not expose its running container"
                )

            pull_requests = lister(container_id)
            if task_marker not in pull_requests:
                raise RuntimeError(
                    "open pull request list does not contain the requested "
                    f"marker for {task.slug}"
                )

            events_url = (
                f"{workspace.host}/api/conversations/{conversation.id}/events"
            )
            events = conversation.list_events()
            _assert_required_events(events)
            _assert_secrets_absent(
                {
                    "pull_requests": pull_requests,
                    "events": [event.model_dump(mode="json") for event in events],
                }
            )
            results.append(
                DockerPiGitHubTaskResult(
                    slug=task.slug,
                    container_id=container_id,
                    conversation_id=conversation.id,
                    conversation_status=conversation.status,
                    repo=target_repo,
                    pull_requests=pull_requests,
                    marker=task_marker,
                    events_url=events_url,
                    events=events,
                )
            )

        if pause:
            for result in results:
                print(f"curl -s {result.events_url}")
            _pause_until_enter()

    return tuple(results)


def _prompt(
    *,
    working_dir: str,
    repo: str,
    task: WebsiteTask,
    marker: str,
    run_id: str,
) -> str:
    branch = f"gg-demo-{task.slug}-{run_id[:8]}"
    return (
        f"You are in empty workspace {working_dir}. "
        "GH_TOKEN is already in the environment. "
        "Use the GitHub CLI (`gh`) for all GitHub access. "
        "Run `gh auth setup-git` once so git can push. "
        "Never print GH_TOKEN, OPENROUTER_API_KEY, or any secret. "
        f"Clone {repo} into {working_dir} with: gh repo clone {repo} . "
        f"Create and switch to a new branch named {branch}. "
        f"Your only product task: {task.instruction} "
        "Inspect the cloned site and edit the existing source files. "
        "Commit the change. "
        "Open a pull request with `gh pr create` whose title contains "
        f"{marker}. "
        "Briefly confirm the PR URL."
    )


def _require_repo(repo: str) -> str:
    value = repo.strip()
    owner, separator, name = value.partition("/")
    if not separator or not owner or not name or "/" in name:
        raise RuntimeError("repo must be OWNER/NAME")
    return value


def _require_secrets() -> None:
    missing = [name for name in SECRET_ENV_NAMES if not os.environ.get(name)]
    if missing:
        names = ", ".join(missing)
        raise RuntimeError(
            f"{names} must be set on the host before the Docker Pi GitHub PR demo"
        )


def _assert_required_events(events: list[Event]) -> None:
    present = {event.kind for event in events}
    missing = sorted(kind.value for kind in REQUIRED_EVENT_KINDS - present)
    if missing:
        raise RuntimeError(
            "conversation is missing required event kinds: " + ", ".join(missing)
        )


def _assert_secrets_absent(value: object) -> None:
    dumped = json.dumps(value, default=str)
    for name in SECRET_ENV_NAMES:
        secret = os.environ.get(name)
        if secret and secret in dumped:
            raise RuntimeError(f"{name} leaked into demo evidence")


def _redact_secrets(text: str) -> str:
    redacted = text
    for name in SECRET_ENV_NAMES:
        secret = os.environ.get(name)
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")
    return redacted


def _read_open_pull_requests(container_id: str) -> str:
    """Return open PR JSON from the container workspace."""
    result = subprocess.run(
        [
            "docker",
            "exec",
            container_id,
            "gh",
            "pr",
            "list",
            "--state",
            "open",
            "--json",
            "url,title,headRefName",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return result.stdout

    detail = _redact_secrets(
        (result.stderr or result.stdout or "pull requests were not readable").strip()
    )
    raise RuntimeError(
        f"open pull requests were not listed in container {container_id}: {detail}"
    )


def _event_summary(events: Sequence[Event]) -> str:
    counts = Counter(event.kind.value for event in events)
    return ", ".join(f"{kind}={counts[kind]}" for kind in sorted(counts))


def _print_output(text: str) -> None:
    print(_redact_secrets(text), end="" if text.endswith("\n") else "\n")


def _pause_until_enter() -> None:
    input("Press Enter to stop the sandboxes.\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run three Pi agents that each open a personal-website pull request."
        )
    )
    parser.add_argument(
        "--repo",
        default=DEFAULT_REPO,
        help=f"GitHub repository to clone (default: {DEFAULT_REPO})",
    )
    parser.add_argument(
        "--image",
        default=DEFAULT_IMAGE,
        help=f"Agent-server image (default: {DEFAULT_IMAGE})",
    )
    args = parser.parse_args()

    results = run_demo(repo=args.repo, image=args.image, pause=True)
    for result in results:
        print(f"{result.slug}: {result.container_id} ({result.conversation_status})")
        print("Open pull requests:")
        _print_output(result.pull_requests)
        print(
            f"Conversation: {result.conversation_id} "
            f"({len(result.events)} events: {_event_summary(result.events)})"
        )


if __name__ == "__main__":
    main()
