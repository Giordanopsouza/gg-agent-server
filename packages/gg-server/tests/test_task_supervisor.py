from __future__ import annotations

import asyncio
import json
import os
import subprocess
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport

from gg.sdk.repository_profiles import RepositoryProfile
from gg.sdk.task_execution import (
    AgentOutcome,
    CheckOutcome,
    StartTaskExecutionRequest,
    TaskExecutionPhase,
)
from gg.server import Settings, create_app


_FAKE_PI = r"""#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path


record_path = Path(os.environ["FAKE_PI_RECORD"])
prompt = json.loads(sys.stdin.buffer.readline())
state = {"prompt": prompt}


def send(message):
    sys.stdout.buffer.write(json.dumps(message).encode() + b"\n")
    sys.stdout.buffer.flush()


send({"id": prompt["id"], "type": "response", "command": "prompt", "success": True})
record_path.with_suffix(".ready").write_text("ready", encoding="utf-8")

if os.environ.get("FAKE_PI_MODE") == "edit":
    Path("README.md").write_text("changed\n", encoding="utf-8")

send({"type": "agent_settled"})
record_path.write_text(json.dumps(state), encoding="utf-8")
raise SystemExit(0)

for raw in sys.stdin.buffer:
    command = json.loads(raw)
    if command["type"] == "abort":
        send({"id": command["id"], "type": "response", "command": "abort", "success": True})
        record_path.write_text(json.dumps(state), encoding="utf-8")
        break
"""


def _git_env() -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        }
    )
    return env


@pytest.fixture
def bare_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "upstream.git"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "--bare", "-b", "main"], cwd=repo, check=True)
    work = tmp_path / "seed"
    work.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=work, check=True)
    (work / "README.md").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=work, check=True, env=_git_env())
    subprocess.run(
        ["git", "commit", "-m", "seed"], cwd=work, check=True, env=_git_env()
    )
    subprocess.run(
        ["git", "remote", "add", "origin", str(repo)],
        cwd=work,
        check=True,
        env=_git_env(),
    )
    subprocess.run(["git", "push", "-u", "origin", "main"], cwd=work, check=True, env=_git_env())
    return repo


@pytest.fixture
def active_pi(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    executable = bin_dir / "pi"
    executable.write_text(_FAKE_PI, encoding="utf-8")
    executable.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("FAKE_PI_MODE", "edit")
    monkeypatch.setenv("FAKE_PI_RECORD", str(tmp_path / "pi-record"))


def _settings(tmp_path: Path, bare_repo: Path) -> Settings:
    profile = RepositoryProfile(
        repository="owner/test",
        bootstrap_command="true",
        check_command="grep -q changed README.md",
    )
    return Settings(
        conversations_dir=tmp_path / "conversations",
        workspace_dir=tmp_path / "workspace",
        task_supervisor_dir=tmp_path / "supervisor",
        repository_profiles=(profile,),
        github_clone_token="test-token",
        process_env={"PATH": os.environ["PATH"], "OPENROUTER_API_KEY": "test-key"},
    )


def _clone_from_bare(
    *,
    repository: str,
    destination: Path,
    github_token: str,
    process_env: dict[str, str],
) -> None:
    del repository, github_token
    bare = os.environ["TEST_BARE_REPO"]
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "clone", bare, str(destination)],
        check=True,
        env=process_env,
    )


def _start_payload(task_id: str = "task-1") -> dict:
    return StartTaskExecutionRequest(
        task_id=task_id,
        repository="owner/test",
        prompt="make a change",
        base_ref="main",
        task_branch=f"gg/task/{task_id}",
        start_key=f"start-{task_id}",
        deadline_at=datetime.now(UTC) + timedelta(hours=1),
    ).model_dump(mode="json")


@pytest.mark.anyio
async def test_start_is_idempotent_and_runs_agent_once(
    tmp_path: Path,
    bare_repo: Path,
    active_pi: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path, bare_repo)
    monkeypatch.setenv("TEST_BARE_REPO", str(bare_repo))
    monkeypatch.setenv(
        "FAKE_PI_WORKDIR", str(settings.workspace_dir / "repos" / "task-1")
    )
    monkeypatch.setattr(
        "gg.server.task_supervisor.service.clone_repository",
        _clone_from_bare,
    )
    app = create_app(settings)
    transport = ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        async with app.router.lifespan_context(app):
            first = await client.post("/api/task-executions/start", json=_start_payload())
            second = await client.post("/api/task-executions/start", json=_start_payload())
            assert first.status_code == 202
            assert second.status_code == 200
            assert first.json()["execution_id"] == second.json()["execution_id"]

            deadline = time.monotonic() + 5
            manifest = None
            while time.monotonic() < deadline:
                response = await client.get(
                    f"/api/task-executions/{first.json()['execution_id']}/manifest"
                )
                if response.status_code == 200:
                    manifest = response.json()
                    break
                await asyncio.sleep(0.05)
            assert manifest is not None
            assert manifest["agent_outcome"] == AgentOutcome.SUCCEEDED.value
            assert manifest["check_outcome"] == CheckOutcome.PASSED.value
            assert manifest["base_sha"]
            assert manifest["changed_files"]
            assert manifest["check_outcome"] == CheckOutcome.PASSED.value


@pytest.mark.anyio
async def test_restart_marks_lost_execution_failed_without_second_agent(
    tmp_path: Path,
    bare_repo: Path,
    active_pi: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_BARE_REPO", str(bare_repo))
    monkeypatch.setattr(
        "gg.server.task_supervisor.service.clone_repository",
        _clone_from_bare,
    )
    settings = _settings(tmp_path, bare_repo)
    monkeypatch.setenv(
        "FAKE_PI_WORKDIR", str(settings.workspace_dir / "repos" / "task-1")
    )
    app = create_app(settings)
    transport = ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        async with app.router.lifespan_context(app):
            started = await client.post("/api/task-executions/start", json=_start_payload())
            execution_id = started.json()["execution_id"]
            await asyncio.sleep(0.2)

    app2 = create_app(settings)
    transport2 = ASGITransport(app=app2)
    async with httpx.AsyncClient(transport=transport2, base_url="http://test") as client:
        async with app2.router.lifespan_context(app2):
            record = await client.get(f"/api/task-executions/{execution_id}")
            assert record.json()["phase"] == TaskExecutionPhase.FAILED.value
            replay = await client.post("/api/task-executions/start", json=_start_payload())
            assert replay.status_code == 200
            assert replay.json()["execution_id"] == execution_id
            assert replay.json()["phase"] == TaskExecutionPhase.FAILED.value


@pytest.mark.anyio
async def test_no_changes_result(
    tmp_path: Path,
    bare_repo: Path,
    active_pi: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_BARE_REPO", str(bare_repo))
    monkeypatch.setenv("FAKE_PI_MODE", "noop")
    settings = _settings(tmp_path, bare_repo)
    monkeypatch.setenv(
        "FAKE_PI_WORKDIR", str(settings.workspace_dir / "repos" / "task-1")
    )
    monkeypatch.setattr(
        "gg.server.task_supervisor.service.clone_repository",
        _clone_from_bare,
    )
    app = create_app(settings)
    transport = ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        async with app.router.lifespan_context(app):
            started = await client.post("/api/task-executions/start", json=_start_payload())
            execution_id = started.json()["execution_id"]
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                record = await client.get(f"/api/task-executions/{execution_id}")
                if record.json()["phase"] in {
                    TaskExecutionPhase.COMPLETED.value,
                    TaskExecutionPhase.FAILED.value,
                }:
                    break
                await asyncio.sleep(0.05)
            manifest = await client.get(
                f"/api/task-executions/{execution_id}/manifest"
            )
            body = manifest.json()
            assert body["agent_outcome"] == AgentOutcome.NO_CHANGES.value
            assert body["check_outcome"] == CheckOutcome.NOT_RUN.value
