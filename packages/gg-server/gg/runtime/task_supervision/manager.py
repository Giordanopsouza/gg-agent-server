"""Control-plane supervision, finalization, archival, and cleanup."""

from __future__ import annotations

import asyncio
import tempfile
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

import httpx

from gg.runtime.ledger import (
    ReservationPhase,
    SandboxProviderState,
    SupervisionRecord,
    TaskLedger,
    TaskResultArchive,
)
from gg.runtime.modal_sandbox import ModalLifecycleError, ModalSandboxLifecycle
from gg.runtime.repo_prep import prepare_repo_from_manifest
from gg.runtime.task_supervisor_client import TaskSupervisorClient
from gg.sdk.domain import Event, MessageDeliveryStatus, MessageReceipt
from gg.sdk.publication import PublicationRequest
from gg.sdk.task_execution import (
    AgentOutcome,
    CheckOutcome,
    StartTaskExecutionRequest,
    TaskExecutionPhase,
    TaskResultManifest,
)
from gg.sdk.task_supervision import TaskEventCopy
from gg.sdk.tasks import TaskState


DEFAULT_TASK_DEADLINE = timedelta(hours=1)
DEFAULT_CLEANUP_BUDGET = timedelta(minutes=5)
TASK_BRANCH_PREFIX = "gg/task"


class PublicationPort(Protocol):
    async def publish(
        self, request: PublicationRequest, *, repo_dir: Path | None = None
    ) -> object: ...


@dataclass(frozen=True)
class SupervisionCallbacks:
    """Optional hooks for tests and integration demos."""

    on_event_copied: Callable[[str, int, Event], None] | None = None


class TaskSupervisionManager:
    """Resume and drive sandbox execution for every reserved task."""

    def __init__(
        self,
        *,
        ledger: TaskLedger,
        lifecycle: ModalSandboxLifecycle,
        settings: object,
        publisher: PublicationPort | None = None,
        callbacks: SupervisionCallbacks | None = None,
    ) -> None:
        self._ledger = ledger
        self._lifecycle = lifecycle
        self._settings = settings
        self._publisher = publisher
        self._callbacks = callbacks or SupervisionCallbacks()
        self._loops: dict[str, asyncio.Task[None]] = {}
        self._live: dict[str, list[asyncio.Queue[TaskEventCopy]]] = defaultdict(list)
        self._settlement_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._stop = asyncio.Event()

    async def startup(self) -> None:
        for reservation in self._ledger.list_reservations():
            if reservation.phase in {
                ReservationPhase.STARTING,
                ReservationPhase.RUNNING,
                ReservationPhase.FINALIZING,
            }:
                self._ensure_loop(reservation.task_id)

    async def shutdown(self) -> None:
        self._stop.set()
        tasks = list(self._loops.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._loops.clear()

    def wake(self) -> None:
        for task_id in list(self._loops):
            self._ensure_loop(task_id)

    def list_event_copies(
        self, task_id: str, *, after_cursor: int = 0
    ) -> list[TaskEventCopy]:
        return [
            TaskEventCopy(
                cursor=cursor,
                source_id=source_id,
                source_seq=source_seq,
                event=event,
            )
            for cursor, source_id, source_seq, event in self._ledger.list_task_events(
                task_id, after_cursor=after_cursor
            )
        ]

    def get_message_receipt(
        self, task_id: str, message_id: str
    ) -> MessageReceipt | None:
        return self._ledger.get_task_message_receipt(task_id, message_id)

    def subscribe_events(self, task_id: str) -> asyncio.Queue[TaskEventCopy]:
        queue: asyncio.Queue[TaskEventCopy] = asyncio.Queue(maxsize=256)
        self._live[task_id].append(queue)
        return queue

    def unsubscribe_events(
        self, task_id: str, queue: asyncio.Queue[TaskEventCopy]
    ) -> None:
        subscribers = self._live.get(task_id, [])
        if queue in subscribers:
            subscribers.remove(queue)

    async def sync_reserved_tasks(self) -> None:
        for reservation in self._ledger.list_reservations():
            if reservation.phase in {
                ReservationPhase.STARTING,
                ReservationPhase.RUNNING,
                ReservationPhase.FINALIZING,
            }:
                self._ensure_loop(reservation.task_id)

    async def send_message(
        self, task_id: str, *, message_id: str, content: str
    ) -> MessageReceipt:
        task = self._ledger.get(task_id)
        if task is None:
            raise KeyError(f"unknown task {task_id}")
        if task.state in {
            TaskState.COMPLETED,
            TaskState.FAILED,
            TaskState.CANCELLED,
            TaskState.FINALIZING,
        }:
            raise RuntimeError("task is not accepting messages")
        existing = self._ledger.get_task_message_receipt(task_id, message_id)
        if existing is not None:
            return existing
        accepted = MessageReceipt(
            id=message_id,
            content=content,
            status=MessageDeliveryStatus.ACCEPTED,
        )
        self._ledger.save_task_message_receipt(task_id, accepted)
        supervision = self._ledger.get_supervision(task_id)
        if supervision is None or supervision.conversation_id is None:
            return accepted
        try:
            connection = await self._lifecycle.connect(task_id)
        except ModalLifecycleError:
            unknown = accepted.model_copy(
                update={
                    "status": MessageDeliveryStatus.UNKNOWN,
                    "detail": "sandbox connection lost before forward",
                    "updated_at": datetime.now(UTC),
                }
            )
            self._ledger.save_task_message_receipt(task_id, unknown)
            return unknown
        async with connection.http_client(timeout=30) as client:
            response = await client.post(
                f"/api/conversations/{supervision.conversation_id}/messages",
                json={"id": message_id, "content": content},
            )
        if response.status_code == 409:
            receipt = MessageReceipt.model_validate(response.json())
            self._ledger.save_task_message_receipt(task_id, receipt)
            return receipt
        response.raise_for_status()
        receipt = MessageReceipt.model_validate(response.json())
        self._ledger.save_task_message_receipt(task_id, receipt)
        return receipt

    def _ensure_loop(self, task_id: str) -> None:
        current = self._loops.get(task_id)
        if current is not None and not current.done():
            return
        self._loops[task_id] = asyncio.create_task(
            self._supervise(task_id), name=f"gg-supervise-{task_id[:8]}"
        )

    async def _supervise(self, task_id: str) -> None:
        try:
            while not self._stop.is_set():
                reservation = self._ledger.get_reservation(task_id)
                if reservation is None:
                    return
                if reservation.phase is ReservationPhase.TERMINATION_PENDING:
                    await self._attempt_cleanup(task_id)
                    await asyncio.sleep(1.0)
                    continue
                if reservation.phase is ReservationPhase.UNRESOLVED_CREATION:
                    return
                if reservation.phase is ReservationPhase.FINALIZING:
                    await self._finalize(task_id)
                    await asyncio.sleep(1.0)
                    continue
                if reservation.phase is ReservationPhase.STARTING:
                    await asyncio.sleep(0.5)
                    continue
                await self._drive_running(task_id)
                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._ledger.update_reservation(
                task_id,
                phase=ReservationPhase.RUNNING,
                condition=f"supervision error: {exc}",
            )

    async def _drive_running(self, task_id: str) -> None:
        task = self._ledger.get(task_id)
        if task is None:
            return
        if task.state is TaskState.QUEUED:
            self._ledger.update_reservation(
                task_id,
                phase=ReservationPhase.RUNNING,
                task_state=TaskState.RUNNING,
            )
        try:
            connection = await self._lifecycle.connect(task_id)
        except ModalLifecycleError as exc:
            self._ledger.update_reservation(
                task_id,
                phase=ReservationPhase.RUNNING,
                condition=f"sandbox connect failed: {exc}",
            )
            return
        client = TaskSupervisorClient(connection)
        supervision = await self._ensure_execution_started(task_id, client)
        if supervision is None:
            return
        if supervision.conversation_id:
            await self._sync_events(task_id, connection, supervision.conversation_id)
        execution = await client.get_execution(supervision.execution_id)
        if supervision.cancel_requested:
            await self._cancel_execution(task_id, connection, supervision, client)
            execution = await client.get_execution(supervision.execution_id)
        if execution.phase in {
            TaskExecutionPhase.COMPLETED,
            TaskExecutionPhase.FAILED,
        }:
            self._ledger.update_reservation(
                task_id,
                phase=ReservationPhase.FINALIZING,
                task_state=TaskState.FINALIZING,
            )

    async def _ensure_execution_started(
        self, task_id: str, client: TaskSupervisorClient
    ) -> SupervisionRecord | None:
        task = self._ledger.get(task_id)
        if task is None:
            return None
        supervision = self._ledger.get_supervision(task_id)
        if supervision is not None and supervision.execution_id != task_id:
            return supervision
        reservation = self._ledger.get_reservation(task_id)
        deadline_at = (
            reservation.reserved_at + DEFAULT_TASK_DEADLINE
            if reservation is not None
            else datetime.now(UTC) + DEFAULT_TASK_DEADLINE
        )
        task_branch = f"{TASK_BRANCH_PREFIX}/{task_id}"
        self._ledger.begin_supervision(
            task_id=task_id,
            execution_id=task_id,
            task_branch=task_branch,
            start_key=task_id,
        )
        request = StartTaskExecutionRequest(
            task_id=task_id,
            repository=task.repository,
            prompt=task.prompt,
            base_ref=task.base_ref,
            task_branch=task_branch,
            start_key=task_id,
            deadline_at=deadline_at,
        )
        try:
            record, _ = await client.start(request)
        except httpx.HTTPError as exc:
            self._ledger.update_reservation(
                task_id,
                phase=ReservationPhase.RUNNING,
                condition=f"execution start failed: {exc}",
            )
            return self._ledger.get_supervision(task_id)
        self._ledger.update_supervision(
            task_id,
            execution_id=record.execution_id,
            conversation_id=record.conversation_id,
        )
        if task.base_sha is None and record.base_ref:
            manifest = await _try_manifest(client, record.execution_id)
            if manifest is not None:
                self._ledger.record_base_sha(task_id, manifest.base_sha)
        return self._ledger.get_supervision(task_id)

    async def _sync_events(
        self, task_id: str, connection: object, conversation_id: str
    ) -> None:
        async with connection.http_client(timeout=30) as client:  # type: ignore[attr-defined]
            response = await client.get(f"/api/conversations/{conversation_id}/events")
        response.raise_for_status()
        for payload in response.json():
            event = Event.model_validate(payload)
            cursor = self._ledger.copy_task_event(
                task_id=task_id,
                source_id=conversation_id,
                source_seq=event.seq,
                event=event,
            )
            if cursor is None:
                continue
            copy = TaskEventCopy(
                cursor=cursor,
                source_id=conversation_id,
                source_seq=event.seq,
                event=event,
            )
            if self._callbacks.on_event_copied:
                self._callbacks.on_event_copied(task_id, cursor, event)
            for queue in self._live.get(task_id, []):
                try:
                    queue.put_nowait(copy)
                except asyncio.QueueFull:
                    pass

    async def _cancel_execution(
        self,
        task_id: str,
        connection: object,
        supervision: SupervisionRecord,
        client: TaskSupervisorClient,
    ) -> None:
        if supervision.conversation_id:
            async with connection.http_client(timeout=30) as client_http:  # type: ignore[attr-defined]
                await client_http.post(
                    f"/api/conversations/{supervision.conversation_id}/cancel"
                )
        record = await client.get_execution(supervision.execution_id)
        if record.phase not in {
            TaskExecutionPhase.COMPLETED,
            TaskExecutionPhase.FAILED,
        }:
            return
        self._ledger.update_reservation(
            task_id,
            phase=ReservationPhase.FINALIZING,
            task_state=TaskState.FINALIZING,
        )

    async def _finalize(self, task_id: str) -> None:
        async with self._settlement_locks[task_id]:
            await self._finalize_locked(task_id)

    async def _finalize_locked(self, task_id: str) -> None:
        task = self._ledger.get(task_id)
        supervision = self._ledger.get_supervision(task_id)
        if task is None or supervision is None:
            return
        if task.state in {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED}:
            await self._attempt_cleanup(task_id)
            return
        try:
            connection = await self._lifecycle.connect(task_id)
        except ModalLifecycleError:
            self._ledger.update_supervision(task_id, tail_gap_possible=True)
            self._ledger.finish_task(
                task_id,
                state=TaskState.FAILED,
                outcome_detail="sandbox lost before finalization completed",
            )
            self._ledger.update_reservation(
                task_id,
                phase=ReservationPhase.TERMINATION_PENDING,
                condition="sandbox lost; cleanup pending",
            )
            return
        client = TaskSupervisorClient(connection)
        await self._settle_messages(task_id, connection, supervision)
        manifest = await _fetch_manifest_with_retries(
            client, supervision.execution_id, budget=DEFAULT_CLEANUP_BUDGET
        )
        evidence_complete = manifest is not None
        evidence_detail = None if evidence_complete else "manifest archival incomplete"
        archive = self._ledger.archive_task_result(
            task_id=task_id,
            execution_id=supervision.execution_id,
            manifest=manifest,
            evidence_complete=evidence_complete,
            evidence_detail=evidence_detail,
        )
        await self._maybe_publish(task_id, manifest, archive)
        terminal_state, outcome_detail, check_status = _terminal_from_manifest(
            task, manifest, supervision.cancel_requested
        )
        self._ledger.finish_task(
            task_id,
            state=terminal_state,
            outcome_detail=outcome_detail,
            check_status=check_status,
        )
        self._ledger.update_reservation(
            task_id,
            phase=ReservationPhase.TERMINATION_PENDING,
            condition=None,
        )

    async def _settle_messages(
        self, task_id: str, connection: object, supervision: SupervisionRecord
    ) -> None:
        if supervision.conversation_id is None:
            for receipt in self._ledger.list_accepted_task_messages(task_id):
                failed = receipt.model_copy(
                    update={
                        "status": MessageDeliveryStatus.FAILED,
                        "detail": "conversation unavailable before settlement",
                        "updated_at": datetime.now(UTC),
                    }
                )
                self._ledger.save_task_message_receipt(task_id, failed)
            return
        for receipt in self._ledger.list_accepted_task_messages(task_id):
            async with connection.http_client(timeout=30) as client:  # type: ignore[attr-defined]
                response = await client.get(
                    f"/api/conversations/{supervision.conversation_id}/messages/{receipt.id}"
                )
            if response.status_code == 404:
                settled = receipt.model_copy(
                    update={
                        "status": MessageDeliveryStatus.FAILED,
                        "detail": "no durable receipt before settlement",
                        "updated_at": datetime.now(UTC),
                    }
                )
            else:
                settled = MessageReceipt.model_validate(response.json())
            self._ledger.save_task_message_receipt(task_id, settled)

    async def _maybe_publish(
        self,
        task_id: str,
        manifest: TaskResultManifest | None,
        archive: TaskResultArchive,
    ) -> None:
        if manifest is None or self._publisher is None:
            return
        request = PublicationRequest(
            task_id=task_id,
            repository=manifest.repository,
            task_branch=manifest.task_branch,
            base_ref=manifest.base_ref,
            base_sha=manifest.base_sha,
            task_marker=task_id,
            agent_outcome=manifest.agent_outcome,
            check_outcome=manifest.check_outcome,
            check=manifest.check,
            changed_files=manifest.changed_files,
        )
        import os

        github_token = getattr(self._settings, "github_clone_token", None)
        if github_token is None:
            return
        with tempfile.TemporaryDirectory(prefix="gg-finalize-") as tmp:
            repo_dir = Path(tmp) / "repo"
            prepare_repo_from_manifest(
                manifest,
                destination=repo_dir,
                github_token=github_token,
                process_env=os.environ,
            )
            result = self._publisher.publish(request, repo_dir=repo_dir)
            if isinstance(result, Awaitable):
                await result

    async def _attempt_cleanup(self, task_id: str) -> None:
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
            self._ledger.release_reservation(task_id, cleanup_status="confirmed_absent")
        else:
            self._ledger.update_reservation(
                task_id,
                phase=ReservationPhase.TERMINATION_PENDING,
                condition=snapshot.detail or "termination not confirmed",
            )


async def _try_manifest(
    client: TaskSupervisorClient, execution_id: str
) -> TaskResultManifest | None:
    try:
        return await client.get_manifest(execution_id)
    except httpx.HTTPError:
        return None


async def _fetch_manifest_with_retries(
    client: TaskSupervisorClient,
    execution_id: str,
    *,
    budget: timedelta,
) -> TaskResultManifest | None:
    deadline = datetime.now(UTC) + budget
    last_error: Exception | None = None
    while datetime.now(UTC) < deadline:
        try:
            return await client.get_manifest(execution_id)
        except httpx.HTTPError as exc:
            last_error = exc
            await asyncio.sleep(0.5)
    if last_error is not None:
        return None
    return None


def _terminal_from_manifest(
    task: object,
    manifest: TaskResultManifest | None,
    cancelled: bool,
) -> tuple[TaskState, str | None, str | None]:
    if cancelled:
        return TaskState.CANCELLED, "cancelled_by_request", None
    if manifest is None:
        return TaskState.FAILED, "missing_manifest", None
    if manifest.agent_outcome is AgentOutcome.NO_CHANGES:
        return TaskState.COMPLETED, "no_changes", manifest.check_outcome.value
    if manifest.agent_outcome is AgentOutcome.CANCELLED:
        return TaskState.CANCELLED, "agent_cancelled", manifest.check_outcome.value
    if manifest.agent_outcome in {
        AgentOutcome.FAILED,
        AgentOutcome.TIMEOUT,
        AgentOutcome.NOT_RUN,
    }:
        return (
            TaskState.FAILED,
            manifest.outcome_detail or manifest.agent_outcome.value,
            manifest.check_outcome.value,
        )
    if manifest.check_outcome is CheckOutcome.FAILED:
        return TaskState.FAILED, "checks_failed", manifest.check_outcome.value
    if manifest.check_outcome is CheckOutcome.PASSED:
        return TaskState.COMPLETED, "checks_passed", manifest.check_outcome.value
    return TaskState.COMPLETED, manifest.outcome_detail, manifest.check_outcome.value


__all__ = ["TaskSupervisionManager", "SupervisionCallbacks", "TASK_BRANCH_PREFIX"]
