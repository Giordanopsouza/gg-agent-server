"""Opt-in live demonstration of reservation, reconnect, and cleanup.

This command owns a private temporary ledger and never accepts coding work.
It requires the same Modal credentials and deployed image as the lifecycle
smoke test. Any resource whose termination cannot be confirmed makes the
command fail.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path
from uuid import uuid4

from gg.runtime.config import load_settings
from gg.runtime.ledger import ReservationPhase, SandboxProviderState, TaskLedger
from gg.runtime.modal_sandbox import lifecycle_from_settings
from gg.runtime.scheduler import TaskScheduler


async def run_demo() -> None:
    settings = load_settings()
    configured_path = os.getenv("GG_LIFECYCLE_DEMO_DB_PATH")
    temporary = None
    if configured_path is None:
        temporary = tempfile.TemporaryDirectory(prefix="gg-lifecycle-demo-")
        db_path = str(Path(temporary.name) / "demo.sqlite")
    else:
        db_path = configured_path

    ledger = TaskLedger(db_path=db_path)
    ledger.open()
    task_id: str | None = None
    scheduler: TaskScheduler | None = None
    try:
        task, _ = ledger.submit(
            idempotency_key=f"lifecycle-demo-{uuid4()}",
            repository="demo/lifecycle-only",
            prompt="lifecycle demonstration; do not execute coding work",
            base_ref=None,
            retry_of=None,
        )
        task_id = task.id
        lifecycle = lifecycle_from_settings(ledger=ledger, settings=settings)
        scheduler = TaskScheduler(
            ledger=ledger,
            lifecycle=lifecycle,
            capacity=1,
            lock_path=f"{db_path}.lock",
            admission_enabled=True,
            poll_seconds=60,
        )
        await scheduler.start()
        await scheduler.dispatch_once()
        reservation = ledger.get_reservation(task.id)
        if reservation is None or reservation.phase is not ReservationPhase.RUNNING:
            raise RuntimeError("demo provisioning did not reach running")

        # Simulate control-plane shutdown: detach without terminating.
        await scheduler.stop()
        scheduler = None

        # A fresh lifecycle/scheduler must adopt the existing provider identity.
        restarted_lifecycle = lifecycle_from_settings(ledger=ledger, settings=settings)
        scheduler = TaskScheduler(
            ledger=ledger,
            lifecycle=restarted_lifecycle,
            capacity=1,
            lock_path=f"{db_path}.lock",
            admission_enabled=False,
            poll_seconds=60,
        )
        await scheduler.start()
        snapshot = await restarted_lifecycle.reconnect(task.id)
        if snapshot.state is not SandboxProviderState.RUNNING:
            raise RuntimeError(f"demo reconnect returned {snapshot.state}")
        ledger.update_reservation(task.id, phase=ReservationPhase.TERMINATION_PENDING)
        await scheduler.reconcile()
        if ledger.get_reservation(task.id) is not None:
            raise RuntimeError("demo cleanup did not confirm provider termination")
    finally:
        if scheduler is not None:
            await scheduler.stop()
        if task_id is not None and ledger.get_reservation(task_id) is not None:
            lifecycle = lifecycle_from_settings(ledger=ledger, settings=settings)
            try:
                snapshot = await lifecycle.terminate(task_id)
            except Exception as exc:
                ledger.close()
                if temporary is not None:
                    temporary.cleanup()
                raise RuntimeError(
                    f"unresolved demo sandbox for task {task_id}"
                ) from exc
            if snapshot.state is not SandboxProviderState.STOPPED:
                ledger.close()
                if temporary is not None:
                    temporary.cleanup()
                raise RuntimeError(
                    f"unresolved demo sandbox for task {task_id}: {snapshot.state}"
                )
            ledger.release_reservation(task_id)
        ledger.close()
        if temporary is not None:
            temporary.cleanup()


def main() -> None:
    asyncio.run(run_demo())


if __name__ == "__main__":
    main()
