"""Regression checks for history, authentication, and event-loop responsiveness."""

from __future__ import annotations

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

import pytest

from gg.runtime.scheduler import TaskScheduler
from gg.sdk.task_execution import AgentOutcome, TaskResultManifest
from gg.sdk.tasks import TaskState
from test_support.sqlite_ledger import new_ledger


USER = "d23bfe09-a12b-49c5-845f-315fc9ec10d6"
SESSION = "75945e5b-9b85-4167-8dc7-ae7ce12276a3"


@pytest.mark.anyio
async def test_slow_scheduler_database_does_not_block_event_loop(tmp_path):
    started, finished, release = threading.Event(), threading.Event(), threading.Event()

    class SlowLedger:
        def settle_successful_tasks(self):
            started.set()
            release.wait(1)
            finished.set()

        def list_reservations(self):
            return []

        def count_queued(self):
            return 0

        def sleeping_workspace_candidates(self, **kwargs):
            return []

    scheduler = TaskScheduler(
        ledger=SlowLedger(),
        lifecycle=None,
        capacity=1,
        lock_path=str(tmp_path / "dispatch.lock"),
    )
    cycle = asyncio.create_task(scheduler.dispatch_once())
    try:
        await asyncio.sleep(0.05)
        assert started.is_set()
        assert not finished.is_set(), "database wait blocked the API event loop"
    finally:
        release.set()
        await cycle


def test_history_outcomes_are_batched_and_owner_scoped():
    with new_ledger() as ledger:
        owner = UUID(USER)
        task, _ = ledger.submit(
            idempotency_key="summary",
            repository=None,
            prompt="work",
            base_ref=None,
            retry_of=None,
            owner_id=owner,
        )
        ledger.archive_task_result(
            task_id=task.id,
            execution_id=None,
            manifest=TaskResultManifest(
                task_id=task.id,
                execution_id=task.id,
                agent_outcome=AgentOutcome.NO_CHANGES,
            ),
            evidence_complete=True,
            evidence_detail=None,
        )
        ledger.finish_task(task.id, state=TaskState.COMPLETED)
        tasks = ledger.list(owner_id=owner)
        assert len(tasks) == 1
        assert tasks[0].agent_outcome == "no_changes"
        assert ledger.list(owner_id=UUID(SESSION)) == []
        # Ledger row mapping must not leak into the shared SQLite connection.
        with ledger.db.read() as connection:
            assert connection.execute("select 1").fetchone() == (1,)


def test_history_reads_do_not_wait_for_the_writer_lock():
    with new_ledger() as ledger:
        with ThreadPoolExecutor(max_workers=1) as worker:
            with ledger.db.write():
                assert worker.submit(ledger.list).result(timeout=2) == []


def test_reopened_connection_keeps_working():
    with new_ledger() as ledger:
        assert ledger.list() == []
    with new_ledger() as reopened:
        assert reopened.list() == []


@pytest.mark.anyio
async def test_idle_scheduler_throttles_retention_and_skips_storage_scan(
    tmp_path, monkeypatch
):
    from gg.runtime import scheduler as scheduler_module

    class IdleLedger:
        def settle_successful_tasks(self):
            pass

        def list_reservations(self):
            return []

        def count_queued(self):
            return 0

        def sleeping_workspace_candidates(self, **kwargs):
            return []

    calls = []
    monkeypatch.setattr(
        scheduler_module, "run_retention_pass", lambda *_: calls.append("retention")
    )

    def unexpected_scan(*_):
        raise AssertionError("no queued task needs an admission storage scan")

    monkeypatch.setattr(scheduler_module, "admission_pressure", unexpected_scan)
    scheduler = TaskScheduler(
        ledger=IdleLedger(),
        lifecycle=None,
        capacity=1,
        lock_path=str(tmp_path / "lock"),
        admission_enabled=True,
        storage_limits=object(),
    )
    await scheduler.dispatch_once()
    await scheduler.dispatch_once()
    assert calls == ["retention"]
    scheduler._last_maintenance -= 61
    await scheduler.dispatch_once()
    assert calls == ["retention", "retention"]
