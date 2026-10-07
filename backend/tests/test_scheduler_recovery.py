from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy.exc import TimeoutError as PoolTimeout

from gg.runtime import RuntimeSettings, create_app
from gg.runtime.readiness import readiness_from_scheduler
from gg.runtime.scheduler import TaskScheduler
from gg.sdk.tasks import TaskState


class QueuedLedger:
    """Keep the queued task visible while testing the real scheduler loop."""

    def open(self):
        pass

    def close(self):
        pass

    def ping_database(self):
        return True

    def settle_successful_tasks(self):
        pass

    def list_reservations(self):
        return []

    def list(self):
        return [SimpleNamespace(state=TaskState.QUEUED)]


@pytest.mark.anyio
@pytest.mark.parametrize("failure", [PoolTimeout, RuntimeError])
async def test_failed_cycle_is_reported_and_retried(tmp_path, caplog, failure):
    ledger = QueuedLedger()
    scheduler = TaskScheduler(
        ledger=ledger,
        lifecycle=object(),
        capacity=10,
        lock_path=str(tmp_path / "dispatch.lock"),
        admission_enabled=True,
        poll_seconds=60,
    )
    failed = asyncio.Event()
    recovered = asyncio.Event()
    attempts = 0

    async def dispatch():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            failed.set()
            raise failure("private database details")
        recovered.set()

    scheduler.dispatch_once = dispatch
    app = create_app(
        RuntimeSettings(api_key="control-secret"),
        task_ledger=ledger,
        modal_lifecycle=object(),
        task_scheduler=scheduler,
    )
    async with app.router.lifespan_context(app):
        await asyncio.wait_for(failed.wait(), timeout=2)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://runtime",
            headers={"X-API-Key": "control-secret"},
        ) as client:
            dispatch_status = await client.get("/tasks/dispatch/status")
            body = dispatch_status.json()
            assert body["running"] is True
            assert body["last_error"] == failure.__name__
            assert body["last_cycle_at"] is not None
            assert body["pending"] == 1
            assert "private database details" not in dispatch_status.text
            readiness = await client.get("/ready")
            assert readiness.status_code == 503
            assert readiness.json()["scheduler_error"] == failure.__name__

            scheduler.wake()
            await asyncio.wait_for(recovered.wait(), timeout=2)
            readiness = await client.get("/ready")
            assert readiness.status_code == 200
            assert readiness.json()["scheduler_running"] is True
            assert readiness.json()["scheduler_error"] is None
            assert attempts == 2
    assert "Task scheduler cycle failed; retrying" in caplog.text
    assert not scheduler.owns_dispatch_lock()


@pytest.mark.anyio
async def test_finished_scheduler_is_not_ready(tmp_path):
    scheduler = TaskScheduler(
        ledger=QueuedLedger(),
        lifecycle=object(),
        capacity=10,
        lock_path=str(tmp_path / "dispatch.lock"),
        admission_enabled=True,
    )
    scheduler._reconciled = True
    scheduler._lock.acquire()
    try:
        scheduler._loop_task = asyncio.create_task(asyncio.sleep(0))
        await scheduler._loop_task
        report = readiness_from_scheduler(scheduler, database_available=True)
        assert report.status == "not_ready"
        assert report.scheduler_running is False
        assert scheduler.status().enabled is True
    finally:
        scheduler._lock.release()
