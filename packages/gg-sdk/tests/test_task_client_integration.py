"""Integration tests for TaskClient against the runtime ASGI app."""

from __future__ import annotations

import sqlite3

from starlette.testclient import TestClient

from gg.runtime import RuntimeSettings, TaskLedger, create_app
from gg.sdk.task_client import TaskClient
from gg.sdk.task_settings import TaskClientSettings
from gg.sdk.tasks import CreateTaskRequest, TaskState


def _settings(tmp_path) -> RuntimeSettings:
    return RuntimeSettings(
        api_key="control-secret",
        task_db_path=str(tmp_path / "tasks.sqlite"),
        dispatch_lock_path=str(tmp_path / "dispatch.lock"),
    )


def _client_settings() -> TaskClientSettings:
    return TaskClientSettings(api_url="http://127.0.0.1:8001", api_key="control-secret")


def test_client_workflow_submit_list_show_cancel(tmp_path) -> None:
    settings = _settings(tmp_path)
    app = create_app(settings, task_ledger=TaskLedger(db_path=settings.task_db_path))

    with TestClient(app, headers={"X-API-Key": "control-secret"}) as http:
        with TaskClient(_client_settings(), client=http) as client:
            submitted = client.submit(
                CreateTaskRequest(
                    repository="owner/repo",
                    base_ref="main",
                    prompt="first",
                    idempotency_key="k1",
                )
            )
            replay = client.submit(
                CreateTaskRequest(
                    repository="owner/repo",
                    base_ref="main",
                    prompt="first",
                    idempotency_key="k1",
                )
            )
            listed = client.list_tasks()
            shown = client.get_task(submitted.record.id)
            cancelled = client.cancel(submitted.record.id)

    assert submitted.created is True
    assert replay.created is False
    assert len(listed) == 1
    assert shown.id == submitted.record.id
    assert cancelled.state is TaskState.CANCELLED


def test_follow_up_submit_uses_prior_branch_without_mutating_original(
    tmp_path,
) -> None:
    settings = _settings(tmp_path)
    ledger = TaskLedger(db_path=settings.task_db_path)
    ledger.open()
    app = create_app(settings, task_ledger=ledger)
    prior_branch = "gg/task/task-original"

    with TestClient(app, headers={"X-API-Key": "control-secret"}) as http:
        with TaskClient(_client_settings(), client=http) as client:
            original = client.submit(
                CreateTaskRequest(
                    repository="owner/repo",
                    base_ref="main",
                    prompt="original work",
                    idempotency_key="k-original",
                )
            )
            with sqlite3.connect(settings.task_db_path) as conn:
                conn.execute(
                    "UPDATE tasks SET state = ? WHERE id = ?",
                    (TaskState.COMPLETED.value, original.record.id),
                )
            ledger.record_base_sha(original.record.id, "deadbeef")
            follow_up = client.submit(
                CreateTaskRequest(
                    repository="owner/repo",
                    prompt="follow-up work",
                    idempotency_key="k-follow",
                    base_ref=prior_branch,
                )
            )
            unchanged = client.get_task(original.record.id)

    assert follow_up.created is True
    assert follow_up.record.id != original.record.id
    assert follow_up.record.base_ref == prior_branch
    assert follow_up.record.prompt == "follow-up work"
    assert unchanged.state is TaskState.COMPLETED
    assert unchanged.prompt == "original work"
