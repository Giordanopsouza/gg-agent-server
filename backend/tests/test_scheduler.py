from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import pytest

from gg.runtime.ledger import (
    ReservationPhase,
    SandboxProviderState,
    TaskLedger,
)
from gg.runtime.modal_sandbox import SandboxSnapshot
from gg.runtime.scheduler import DeploymentLock, DispatchLockError, TaskScheduler
from gg.sdk.tasks import TaskState


def _submit(ledger: TaskLedger, key: str):
    return ledger.submit(
        idempotency_key=key,
        repository="owner/repo",
        prompt="work",
        base_ref=None,
        retry_of=None,
    )[0]


def _record_creation(
    ledger: TaskLedger, task_id: str, *, provider_id: str | None
) -> None:
    ledger.begin_sandbox_creation(
        task_id=task_id,
        deployment="production",
        sandbox_name=f"sandbox-{task_id}",
        tags_json=f'{{"gg_task_id":"{task_id}"}}',
        session_api_key="private",
    )
    if provider_id is not None:
        ledger.update_sandbox_creation(
            task_id,
            provider_id=provider_id,
            provider_state=SandboxProviderState.RUNNING,
        )


@dataclass
class FakeLifecycle:
    ledger: TaskLedger
    state: SandboxProviderState = SandboxProviderState.RUNNING
    adopt_on_reconnect: bool = False

    def __post_init__(self) -> None:
        self.create_calls: list[str] = []
        self.reconnect_calls: list[str] = []
        self.detach_calls: list[str] = []
        self.terminate_calls: list[str] = []

    async def create(self, task_id: str) -> SandboxSnapshot:
        self.create_calls.append(task_id)
        if self.ledger.get_sandbox_creation(task_id) is None:
            _record_creation(self.ledger, task_id, provider_id="created-provider")
        return SandboxSnapshot(task_id, "created-provider", self.state)

    async def reconnect(self, task_id: str) -> SandboxSnapshot:
        self.reconnect_calls.append(task_id)
        if self.adopt_on_reconnect:
            self.ledger.update_sandbox_creation(
                task_id,
                provider_id="adopted-provider",
                provider_state=SandboxProviderState.RUNNING,
            )
        creation = self.ledger.get_sandbox_creation(task_id)
        provider_id = creation.provider_id if creation else None
        return SandboxSnapshot(task_id, provider_id, self.state, "provider condition")

    async def detach(self, task_id: str) -> SandboxSnapshot:
        self.detach_calls.append(task_id)
        creation = self.ledger.get_sandbox_creation(task_id)
        return SandboxSnapshot(
            task_id, creation.provider_id if creation else None, self.state
        )

    async def terminate(self, task_id: str) -> SandboxSnapshot:
        self.terminate_calls.append(task_id)
        return SandboxSnapshot(task_id, "provider", SandboxProviderState.STOPPED)


def test_deployment_lock_rejects_second_local_owner(tmp_path) -> None:
    first = DeploymentLock(str(tmp_path / "dispatch.lock"))
    second = DeploymentLock(str(tmp_path / "dispatch.lock"))
    first.acquire()
    try:
        with pytest.raises(DispatchLockError, match="already owned"):
            second.acquire()
    finally:
        first.release()

    second.acquire()
    second.release()


def test_concurrent_claims_are_fifo_unique_and_bounded_to_ten(tmp_path) -> None:
    with TaskLedger(db_path=str(tmp_path / "tasks.sqlite")) as ledger:
        tasks = [_submit(ledger, f"task-{number}") for number in range(12)]

        with ThreadPoolExecutor(max_workers=16) as pool:
            claimed = list(
                pool.map(lambda _: ledger.reserve_next(capacity=10), range(24))
            )

        claimed_records = [record for record in claimed if record is not None]
        assert {record.id for record in claimed_records} == {
            task.id for task in tasks[:10]
        }
        assert len(claimed_records) == 10
        assert len(ledger.list_reservations()) == 10
        assert [task.state for task in ledger.list()] == [
            *([TaskState.STARTING] * 10),
            TaskState.QUEUED,
            TaskState.QUEUED,
        ]


@pytest.mark.anyio
async def test_recovery_after_crash_before_creation_provisions_once(tmp_path) -> None:
    with TaskLedger(db_path=str(tmp_path / "tasks.sqlite")) as ledger:
        task = _submit(ledger, "before-create")
        ledger.reserve_next(capacity=1)
        lifecycle = FakeLifecycle(ledger)
        scheduler = TaskScheduler(
            ledger=ledger,
            lifecycle=lifecycle,  # type: ignore[arg-type]
            capacity=1,
            lock_path=str(tmp_path / "lock"),
            admission_enabled=True,
        )

        await scheduler.dispatch_once()

        assert lifecycle.create_calls == [task.id]
        assert ledger.get(task.id).state is TaskState.RUNNING  # type: ignore[union-attr]


@pytest.mark.anyio
async def test_recovery_adopts_create_lost_before_id_persistence(tmp_path) -> None:
    with TaskLedger(db_path=str(tmp_path / "tasks.sqlite")) as ledger:
        task = _submit(ledger, "after-provider-create")
        ledger.reserve_next(capacity=1)
        _record_creation(ledger, task.id, provider_id=None)
        lifecycle = FakeLifecycle(ledger, adopt_on_reconnect=True)
        scheduler = TaskScheduler(
            ledger=ledger,
            lifecycle=lifecycle,  # type: ignore[arg-type]
            capacity=1,
            lock_path=str(tmp_path / "lock"),
            admission_enabled=True,
        )

        await scheduler.dispatch_once()

        assert lifecycle.reconnect_calls == [task.id]
        assert lifecycle.create_calls == []
        creation = ledger.get_sandbox_creation(task.id)
        assert creation is not None
        assert creation.provider_id == "adopted-provider"
        assert ledger.get_reservation(task.id).phase is ReservationPhase.RUNNING  # type: ignore[union-attr]


@pytest.mark.anyio
async def test_recovery_during_running_reconnects_without_reprovision(tmp_path) -> None:
    with TaskLedger(db_path=str(tmp_path / "tasks.sqlite")) as ledger:
        task = _submit(ledger, "during-running")
        ledger.reserve_next(capacity=1)
        _record_creation(ledger, task.id, provider_id="running-provider")
        lifecycle = FakeLifecycle(ledger)
        scheduler = TaskScheduler(
            ledger=ledger,
            lifecycle=lifecycle,  # type: ignore[arg-type]
            capacity=1,
            lock_path=str(tmp_path / "lock"),
            admission_enabled=True,
        )

        await scheduler.dispatch_once()

        assert lifecycle.reconnect_calls == [task.id]
        assert lifecycle.create_calls == []
        assert ledger.get(task.id).state is TaskState.RUNNING  # type: ignore[union-attr]


@pytest.mark.anyio
async def test_recovery_during_termination_confirms_absence_before_release(
    tmp_path,
) -> None:
    with TaskLedger(db_path=str(tmp_path / "tasks.sqlite")) as ledger:
        task = _submit(ledger, "during-termination")
        ledger.reserve_next(capacity=1)
        _record_creation(ledger, task.id, provider_id="stopping-provider")
        ledger.update_reservation(task.id, phase=ReservationPhase.TERMINATION_PENDING)
        lifecycle = FakeLifecycle(ledger)
        scheduler = TaskScheduler(
            ledger=ledger,
            lifecycle=lifecycle,  # type: ignore[arg-type]
            capacity=1,
            lock_path=str(tmp_path / "lock"),
            admission_enabled=False,
        )

        await scheduler.reconcile()

        assert lifecycle.terminate_calls == [task.id]
        assert ledger.get_reservation(task.id) is None
        assert ledger.get(task.id).sandbox_cleanup_status == "confirmed_absent"  # type: ignore[union-attr]


@pytest.mark.anyio
async def test_unknown_reconciliation_blocks_capacity_and_is_visible(tmp_path) -> None:
    with TaskLedger(db_path=str(tmp_path / "tasks.sqlite")) as ledger:
        first = _submit(ledger, "unknown")
        second = _submit(ledger, "waiting")
        ledger.reserve_next(capacity=1)
        _record_creation(ledger, first.id, provider_id="unknown-provider")
        lifecycle = FakeLifecycle(ledger, state=SandboxProviderState.UNKNOWN)
        scheduler = TaskScheduler(
            ledger=ledger,
            lifecycle=lifecycle,  # type: ignore[arg-type]
            capacity=1,
            lock_path=str(tmp_path / "lock"),
            admission_enabled=True,
        )

        await scheduler.dispatch_once()

        assert ledger.get(second.id).state is TaskState.QUEUED  # type: ignore[union-attr]
        status = scheduler.status()
        assert status.reserved == 1
        assert status.pending == 1
        assert status.conditions[0].task_id == first.id


@pytest.mark.anyio
async def test_confirmed_sandbox_loss_fails_without_erasing_evidence(tmp_path) -> None:
    with TaskLedger(db_path=str(tmp_path / "tasks.sqlite")) as ledger:
        task = _submit(ledger, "lost")
        ledger.reserve_next(capacity=1)
        _record_creation(ledger, task.id, provider_id="lost-provider")
        assert ledger._conn is not None  # noqa: SLF001
        ledger._conn.execute(  # noqa: SLF001
            "UPDATE tasks SET outcome_detail = ?, check_status = ? WHERE id = ?",
            ("captured output", "not_run", task.id),
        )
        lifecycle = FakeLifecycle(ledger, state=SandboxProviderState.STOPPED)
        scheduler = TaskScheduler(
            ledger=ledger,
            lifecycle=lifecycle,  # type: ignore[arg-type]
            capacity=1,
            lock_path=str(tmp_path / "lock"),
        )

        await scheduler.reconcile()

        failed = ledger.get(task.id)
        assert failed is not None
        assert failed.state is TaskState.FAILED
        assert failed.outcome_detail == "captured output"
        assert failed.check_status == "not_run"
        assert ledger.get_reservation(task.id) is None


@pytest.mark.anyio
async def test_reconcile_keeps_published_task_completed_when_sandbox_stops(
    tmp_path,
) -> None:
    with TaskLedger(db_path=str(tmp_path / "tasks.sqlite")) as ledger:
        task = _submit(ledger, "published-then-stopped")
        ledger.reserve_next(capacity=1)
        _record_creation(ledger, task.id, provider_id="published-provider")
        ledger.finish_task(
            task.id, state=TaskState.COMPLETED, outcome_detail="published"
        )
        lifecycle = FakeLifecycle(ledger, state=SandboxProviderState.STOPPED)
        scheduler = TaskScheduler(
            ledger=ledger,
            lifecycle=lifecycle,  # type: ignore[arg-type]
            capacity=1,
            lock_path=str(tmp_path / "lock"),
        )

        await scheduler.reconcile()

        settled = ledger.get(task.id)
        assert settled is not None
        assert settled.state is TaskState.COMPLETED
        assert settled.outcome_detail == "published"


@pytest.mark.anyio
async def test_reconcile_does_not_demote_completed_task_while_sandbox_runs(
    tmp_path,
) -> None:
    with TaskLedger(db_path=str(tmp_path / "tasks.sqlite")) as ledger:
        task = _submit(ledger, "published-still-running")
        ledger.reserve_next(capacity=1)
        _record_creation(ledger, task.id, provider_id="running-provider")
        ledger.update_reservation(task.id, phase=ReservationPhase.FINALIZING)
        ledger.finish_task(
            task.id, state=TaskState.COMPLETED, outcome_detail="published"
        )
        lifecycle = FakeLifecycle(ledger, state=SandboxProviderState.RUNNING)
        scheduler = TaskScheduler(
            ledger=ledger,
            lifecycle=lifecycle,  # type: ignore[arg-type]
            capacity=1,
            lock_path=str(tmp_path / "lock"),
        )

        await scheduler.reconcile()

        settled = ledger.get(task.id)
        assert settled is not None
        assert settled.state is TaskState.COMPLETED


@pytest.mark.anyio
async def test_reconcile_completes_published_task_stuck_after_cleanup(
    tmp_path,
) -> None:
    with TaskLedger(db_path=str(tmp_path / "tasks.sqlite")) as ledger:
        task = _submit(ledger, "stuck-finalizing")
        ledger.reserve_next(capacity=1)
        ledger.finish_task(
            task.id, state=TaskState.FINALIZING, outcome_detail="published"
        )
        ledger.release_reservation(task.id)
        scheduler = TaskScheduler(
            ledger=ledger,
            lifecycle=FakeLifecycle(ledger),  # type: ignore[arg-type]
            capacity=1,
            lock_path=str(tmp_path / "lock"),
        )

        await scheduler.reconcile()

        settled = ledger.get(task.id)
        assert settled is not None
        assert settled.state is TaskState.COMPLETED
        assert settled.outcome_detail == "published"
