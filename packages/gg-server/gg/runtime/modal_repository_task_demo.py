"""Opt-in Modal demo for repository task execution and test evidence."""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from gg.runtime.config import load_settings
from gg.runtime.ledger import TaskLedger
from gg.runtime.modal_sandbox import lifecycle_from_settings
from gg.runtime.task_supervisor_client import TaskSupervisorClient
from gg.sdk.task_execution import StartTaskExecutionRequest, TaskExecutionPhase


async def run_demo() -> None:
    settings = load_settings()
    if not settings.repository_profiles:
        raise RuntimeError("GG_REPOSITORY_PROFILES_PATH must configure one profile")
    profile = settings.repository_profiles[0]
    ledger = TaskLedger(db_path=os.getenv("GG_REPOSITORY_DEMO_DB_PATH", ":memory:"))
    ledger.open()
    task_id = str(uuid4())
    task, _ = ledger.submit(
        idempotency_key=f"repository-demo-{task_id}",
        repository=profile.repository,
        prompt=os.getenv(
            "GG_REPOSITORY_DEMO_PROMPT",
            "Add a clearly labeled demo marker file and nothing else.",
        ),
        base_ref=None,
        retry_of=None,
    )
    lifecycle = lifecycle_from_settings(ledger=ledger, settings=settings)
    try:
        await lifecycle.create(task.id)
        connection = await lifecycle.connect(task.id)
        client = TaskSupervisorClient(connection)
        request = StartTaskExecutionRequest(
            task_id=task.id,
            repository=profile.repository,
            prompt=task.prompt,
            base_ref=None,
            task_branch=f"gg/demo/{task.id}",
            start_key=task.id,
            deadline_at=datetime.now(UTC) + timedelta(hours=1),
        )
        record, status_code = await client.start(request)
        print(f"start status={status_code} execution_id={record.execution_id}")
        while True:
            current = await client.get_execution(record.execution_id)
            print(f"phase={current.phase}")
            if current.phase in {
                TaskExecutionPhase.COMPLETED,
                TaskExecutionPhase.FAILED,
            }:
                break
            await asyncio.sleep(5)
        manifest = await client.get_manifest(record.execution_id)
        print(manifest.model_dump_json(indent=2))
    finally:
        try:
            await lifecycle.terminate(task.id)
        finally:
            ledger.close()


def main() -> None:
    asyncio.run(run_demo())


if __name__ == "__main__":
    main()
