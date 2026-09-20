from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime

import httpx
import pytest
from click.testing import CliRunner

import gg.sdk.cli.main as main_module
from gg.sdk.cli import output as out
from gg.sdk.cli.main import main
from gg.sdk.task_client import TaskClient
from gg.sdk.task_settings import TaskClientSettings


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GG_RUNTIME_API_KEY", "control-secret")
    monkeypatch.setenv("GG_TASK_API_URL", "http://127.0.0.1:8001")


def _settings() -> TaskClientSettings:
    return TaskClientSettings(api_url="http://127.0.0.1:8001", api_key="control-secret")


def _patch_open_client(
    monkeypatch: pytest.MonkeyPatch, handler: Callable[[httpx.Request], httpx.Response]
) -> None:
    transport = httpx.MockTransport(handler)
    http = httpx.Client(
        transport=transport,
        base_url="http://127.0.0.1:8001",
        timeout=30.0,
    )
    client = TaskClient(_settings(), client=http)

    class _ClientContext(AbstractContextManager[TaskClient]):
        def __enter__(self) -> TaskClient:
            return client

        def __exit__(self, *_: object) -> None:
            client.close()

    monkeypatch.setattr(main_module, "_open_client", _ClientContext)


def _task_payload(task_id: str = "task-1", state: str = "queued") -> dict:
    now = datetime.now(UTC).isoformat()
    return {
        "id": task_id,
        "seq": 1,
        "state": state,
        "idempotency_key": "k1",
        "repository": "owner/repo",
        "prompt": "fix",
        "base_ref": None,
        "base_sha": None,
        "retry_of": None,
        "created_at": now,
        "updated_at": now,
        "outcome_detail": None,
        "check_status": None,
        "sandbox_cleanup_status": None,
    }


def test_submit_emits_idempotency_key_on_stderr(
    runner: CliRunner, env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/tasks"
        return httpx.Response(201, json=_task_payload())

    _patch_open_client(monkeypatch, handle)

    result = runner.invoke(
        main,
        [
            "submit",
            "--repository",
            "owner/repo",
            "--prompt",
            "fix",
            "--idempotency-key",
            "k1",
        ],
    )

    assert result.exit_code == out.EXIT_OK
    assert "idempotency_key: k1" in result.output
    assert "state=queued" in result.output


def test_submit_json_output(
    runner: CliRunner, env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json=_task_payload())

    _patch_open_client(monkeypatch, handle)

    result = runner.invoke(
        main,
        ["--json", "submit", "--repository", "owner/repo", "--prompt", "fix"],
    )

    assert result.exit_code == out.EXIT_OK
    payload = json.loads(result.output.strip().splitlines()[0])
    assert payload["ok"] is True
    assert payload["created"] is True
    assert "idempotency_key" in payload


def test_result_exit_code_distinguishes_failed_task(
    runner: CliRunner, env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    states = iter(["running", "failed"])

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/result"):
            return httpx.Response(
                200,
                json={
                    "task_id": "task-1",
                    "state": "failed",
                    "execution_id": None,
                    "manifest": None,
                    "publication": None,
                    "evidence_complete": False,
                    "evidence_detail": None,
                    "sandbox_cleanup_status": None,
                    "outcome_detail": "boom",
                    "check_status": None,
                    "retry_of": None,
                    "prior_task_branch": None,
                    "prior_pr_url": None,
                    "updated_at": datetime.now(UTC).isoformat(),
                },
            )
        state = next(states)
        return httpx.Response(200, json=_task_payload(state=state))

    _patch_open_client(monkeypatch, handle)

    result = runner.invoke(main, ["result", "task-1", "--wait"])

    assert result.exit_code == out.EXIT_TASK_UNSUCCESSFUL
    assert "state=failed" in result.output


def test_message_rejects_completed_task_without_api_call(
    runner: CliRunner, env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/messages"):
            raise AssertionError("message endpoint should not be called")
        return httpx.Response(200, json=_task_payload(state="completed"))

    _patch_open_client(monkeypatch, handle)

    result = runner.invoke(main, ["message", "task-1", "hello"])

    assert result.exit_code == out.EXIT_COMMAND_FAILED
    assert "not accepting messages" in result.output
