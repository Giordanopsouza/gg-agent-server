"""Single-host FIFO reservation, recovery, and demo-only provisioning.

Production admission provisions sandboxes and hands reserved tasks to the
supervision manager for execution, finalization, archival, and cleanup.
Recovery still runs at process startup so existing ownership remains visible
and surviving sandboxes are adopted.
"""

from __future__ import annotations

import asyncio
import fcntl
import hashlib
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from gg.runtime.ledger import (
    ReservationPhase,
    SandboxProviderState,
    TaskLedger,
)
from gg.runtime.modal_sandbox import (
    AmbiguousProviderStateError,
    ConflictingSandboxesError,
    ModalLifecycleError,
    ModalSandboxLifecycle,
)
from gg.runtime.task_supervision.manager import TaskSupervisionManager
from gg.sdk.tasks import TaskState


class DispatchLockError(RuntimeError):
    """Another local control-plane process owns this deployment."""


class DispatchCondition(BaseModel):
    model_config = ConfigDict(frozen=True)

    task_id: str
    phase: ReservationPhase
    detail: str


class DispatchStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    enabled: bool
    reconciled: bool
    capacity: int
    reserved: int
    pending: int
    disabled_reason: str | None = None
    conditions: tuple[DispatchCondition, ...] = ()


def default_lock_path(*, db_path: str, deployment: str) -> str:
    """Return a stable lock path for the local deployment."""

    if db_path != ":memory:":
        return f"{db_path}.dispatch.lock"
    digest = hashlib.sha256(deployment.encode()).hexdigest()[:16]
    return f"/tmp/gg-dispatch-{digest}.lock"


class DeploymentLock:
    """Non-blocking advisory lock held for the scheduler lifespan."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._fd: int | None = None

    def acquire(self) -> None:
        if self._fd is not None:
            return
        path = Path(self.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        os.chmod(path, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            os.close(fd)
            raise DispatchLockError(
                f"deployment dispatch is already owned; lock={self.path}"
            ) from exc
        self._fd = fd

    def release(self) -> None:
        if self._fd is None:
            return
        fcntl.flock(self._fd, fcntl.LOCK_UN)
        os.close(self._fd)
        self._fd = None


class TaskScheduler:
    """Lifespan-managed reconciler and FIFO sandbox provisioner."""

    def __init__(
        self,
        *,
        ledger: TaskLedger,
        lifecycle: ModalSandboxLifecycle,
        capacity: int,
        lock_path: str,
        admission_enabled: bool = False,
        poll_seconds: float = 1.0,
        supervision: TaskSupervisionManager | None = None,
    ) -> None:
        if not 1 <= capacity <= 10:
            raise ValueError("scheduler capacity must be between 1 and 10")
        self._ledger = ledger
        self._lifecycle = lifecycle
        self._capacity = capacity
        self._admission_enabled = admission_enabled
        self._poll_seconds = poll_seconds
        self._supervision = supervision
        self._lock = DeploymentLock(lock_path)
        self._stop = asyncio.Event()
        self._wake = asyncio.Event()
        self._loop_task: asyncio.Task[None] | None = None
        self._reconciled = False
        self._cycle_lock = asyncio.Lock()

    async def start(self) -> None:
        """Take exclusive ownership and reconcile before starting admission."""

        self._lock.acquire()
        try:
            await self.reconcile()
        except BaseException:
            self._lock.release()
            raise
        self._loop_task = asyncio.create_task(self._run(), name="gg-task-scheduler")

    async def stop(self) -> None:
        """Stop admission and detach, never terminate, surviving sandboxes."""

        self._stop.set()
        self._wake.set()
        try:
            if self._loop_task is not None:
                await self._loop_task
                self._loop_task = None
            for reservation in self._ledger.list_reservations():
                if self._ledger.get_sandbox_creation(reservation.task_id) is None:
                    continue
                try:
                    snapshot = await self._lifecycle.detach(reservation.task_id)
                    if snapshot.state is SandboxProviderState.STOPPED:
                        if reservation.phase is ReservationPhase.TERMINATION_PENDING:
                            self._ledger.release_reservation(reservation.task_id)
                        else:
                            self._ledger.mark_sandbox_lost(
                                reservation.task_id,
                                detail=snapshot.detail
                                or "sandbox was confirmed lost during shutdown",
                            )
                    elif snapshot.state is SandboxProviderState.UNKNOWN:
                        self._ledger.update_reservation(
                            reservation.task_id,
                            phase=reservation.phase,
                            condition=snapshot.detail or "detach state is unknown",
                        )
                except ModalLifecycleError as exc:
                    self._ledger.update_reservation(
                        reservation.task_id,
                        phase=reservation.phase,
                        condition=f"detach unresolved: {exc}",
                    )
        finally:
            self._lock.release()

    def wake(self) -> None:
        self._wake.set()

    async def _run(self) -> None:
        while not self._stop.is_set():
            await self.dispatch_once()
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=self._poll_seconds)
            except TimeoutError:
                pass
            self._wake.clear()

    async def dispatch_once(self) -> None:
        """Reconcile ownership, then fill available slots in durable FIFO order."""

        async with self._cycle_lock:
            await self.reconcile()
            if not self._admission_enabled or self._stop.is_set():
                return
            if self._supervision is not None:
                await self._supervision.sync_reserved_tasks()
            # Resume reservations that crashed before a provider identity was
            # established before admitting any additional queued work.
            for reservation in self._ledger.list_reservations():
                if reservation.phase is not ReservationPhase.STARTING:
                    continue
                await self._provision(reservation.task_id)
                if self._stop.is_set():
                    return
            while not self._stop.is_set():
                task = self._ledger.reserve_next(capacity=self._capacity)
                if task is None:
                    return
                await self._provision(task.id)

    async def reconcile(self) -> None:
        """Resolve every existing reservation before any new task is admitted."""

        for reservation in self._ledger.list_reservations():
            creation = self._ledger.get_sandbox_creation(reservation.task_id)
            if creation is None:
                if reservation.phase is ReservationPhase.TERMINATION_PENDING:
                    self._ledger.release_reservation(reservation.task_id)
                else:
                    # Crash before the provider call: creation is safe to begin.
                    self._ledger.update_reservation(
                        reservation.task_id,
                        phase=ReservationPhase.STARTING,
                        condition=None,
                    )
                continue
            try:
                snapshot = await self._lifecycle.reconnect(reservation.task_id)
            except ConflictingSandboxesError as exc:
                self._ledger.update_reservation(
                    reservation.task_id,
                    phase=ReservationPhase.UNRESOLVED_CREATION,
                    condition=f"conflicting provider identity: {exc}",
                )
                continue
            except ModalLifecycleError as exc:
                self._ledger.update_reservation(
                    reservation.task_id,
                    phase=ReservationPhase.UNRESOLVED_CREATION,
                    condition=f"provider reconciliation failed: {exc}",
                )
                continue

            if snapshot.state is SandboxProviderState.UNKNOWN:
                self._ledger.update_reservation(
                    reservation.task_id,
                    phase=ReservationPhase.UNRESOLVED_CREATION,
                    condition=snapshot.detail or "provider state is unknown",
                )
                continue

            if snapshot.state is SandboxProviderState.STOPPED:
                if reservation.phase is ReservationPhase.TERMINATION_PENDING:
                    self._ledger.release_reservation(reservation.task_id)
                elif creation.provider_id is None:
                    # Absence was established by deterministic identity lookup;
                    # a create attempt can now be made without duplication.
                    self._ledger.update_reservation(
                        reservation.task_id,
                        phase=ReservationPhase.STARTING,
                        condition=None,
                    )
                else:
                    self._ledger.mark_sandbox_lost(
                        reservation.task_id,
                        detail=snapshot.detail or "sandbox was confirmed lost",
                    )
                continue

            if reservation.phase is ReservationPhase.TERMINATION_PENDING:
                await self._terminate_reserved(reservation.task_id)
                continue
            phase = (
                ReservationPhase.FINALIZING
                if reservation.phase is ReservationPhase.FINALIZING
                else ReservationPhase.RUNNING
            )
            state = (
                TaskState.FINALIZING
                if phase is ReservationPhase.FINALIZING
                else TaskState.RUNNING
            )
            self._ledger.update_reservation(
                reservation.task_id,
                phase=phase,
                condition=None,
                task_state=state,
            )
        self._reconciled = True

    async def _provision(self, task_id: str) -> None:
        try:
            snapshot = await self._lifecycle.create(task_id)
        except AmbiguousProviderStateError as exc:
            self._ledger.update_reservation(
                task_id,
                phase=ReservationPhase.UNRESOLVED_CREATION,
                condition=str(exc),
            )
            return
        except ModalLifecycleError as exc:
            self._ledger.update_reservation(
                task_id,
                phase=ReservationPhase.UNRESOLVED_CREATION,
                condition=f"provisioning failed: {exc}",
            )
            return
        if snapshot.state is SandboxProviderState.RUNNING:
            self._ledger.update_reservation(
                task_id,
                phase=ReservationPhase.RUNNING,
                condition=None,
                task_state=TaskState.RUNNING,
            )
        else:
            self._ledger.update_reservation(
                task_id,
                phase=ReservationPhase.UNRESOLVED_CREATION,
                condition=snapshot.detail or "provisioning did not establish running",
            )

    async def _terminate_reserved(self, task_id: str) -> None:
        try:
            snapshot = await self._lifecycle.terminate(task_id)
        except ModalLifecycleError as exc:
            self._ledger.update_reservation(
                task_id,
                phase=ReservationPhase.TERMINATION_PENDING,
                condition=f"termination unresolved: {exc}",
            )
            return
        if snapshot.state is SandboxProviderState.STOPPED:
            self._ledger.release_reservation(task_id)
        else:
            self._ledger.update_reservation(
                task_id,
                phase=ReservationPhase.TERMINATION_PENDING,
                condition=snapshot.detail or "termination is not confirmed",
            )

    def status(self) -> DispatchStatus:
        reservations = self._ledger.list_reservations()
        conditions = tuple(
            DispatchCondition(
                task_id=item.task_id,
                phase=item.phase,
                detail=item.condition,
            )
            for item in reservations
            if item.condition is not None
        )
        pending = sum(
            1 for task in self._ledger.list() if task.state is TaskState.QUEUED
        )
        return DispatchStatus(
            enabled=self._admission_enabled,
            reconciled=self._reconciled,
            capacity=self._capacity,
            reserved=len(reservations),
            pending=pending,
            disabled_reason=None if self._admission_enabled else "dispatch disabled",
            conditions=conditions,
        )


__all__ = [
    "DeploymentLock",
    "DispatchCondition",
    "DispatchLockError",
    "DispatchStatus",
    "TaskScheduler",
    "default_lock_path",
]
