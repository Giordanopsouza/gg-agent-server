"""Control-plane supervision, finalization, archival, and cleanup."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx

from gg.runtime.config import RuntimeSettings
from gg.runtime.ledger import (
    ReservationPhase,
    SandboxProviderState,
    SupervisionRecord,
    TaskLedger,
)
from gg.runtime.modal_sandbox import ModalLifecycleError, ModalSandboxLifecycle
from gg.runtime.repository_authorization import (
    RepositoryAccessError,
    RepositoryAuthorization,
)
from gg.runtime.storage import (
    StorageLimits,
    measure_task_evidence,
    truncate_event_json,
    truncate_manifest,
)
from gg.runtime.task_supervisor_client import TaskSupervisorClient
from gg.sdk.domain import Event, MessageDeliveryStatus, MessageReceipt
from gg.sdk.task_execution import (
    AgentOutcome,
    CheckOutcome,
    StartTaskExecutionRequest,
    TaskExecutionPhase,
    TaskResultManifest,
)
from gg.sdk.task_supervision import TaskEventCopy
from gg.sdk.tasks import TaskRecord, TaskState


DEFAULT_TASK_DEADLINE = timedelta(hours=1)
DEFAULT_CLEANUP_BUDGET = timedelta(minutes=5)
TASK_BRANCH_PREFIX = "gg/task"


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
        settings: RuntimeSettings | object,
        callbacks: SupervisionCallbacks | None = None,
        repository_authorization: RepositoryAuthorization | None = None,
    ) -> None:
        self._ledger = ledger
        self._lifecycle = lifecycle
        self._settings = settings
        self._storage_limits = (
            StorageLimits.from_settings(settings)
            if isinstance(settings, RuntimeSettings)
            else None
        )
        self._repository_authorization = repository_authorization
        self._callbacks = callbacks or SupervisionCallbacks()
        self._loops: dict[str, asyncio.Task[None]] = {}
        self._live: dict[str, list[asyncio.Queue[TaskEventCopy]]] = defaultdict(list)
        self._settlement_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._workspace_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._stop = asyncio.Event()

    async def startup(self) -> None:
        for reservation in await asyncio.to_thread(self._ledger.list_reservations):
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
        for reservation in await asyncio.to_thread(self._ledger.list_reservations):
            if reservation.phase in {
                ReservationPhase.STARTING,
                ReservationPhase.RUNNING,
                ReservationPhase.FINALIZING,
            }:
                self._ensure_loop(reservation.task_id)

    async def send_message(
        self, task_id: str, *, message_id: str, content: str
    ) -> MessageReceipt:
        task = await asyncio.to_thread(self._ledger.get, task_id)
        if task is None:
            raise KeyError(f"unknown task {task_id}")
        if task.owner_id is not None and task.repository is not None:
            if self._repository_authorization is None:
                raise RuntimeError("GitHub repository authorization unavailable")
            try:
                await asyncio.to_thread(
                    self._repository_authorization.resolve,
                    task.owner_id,
                    task.repository,
                    task.base_ref or "",
                )
            except ValueError as exc:
                raise RuntimeError(str(exc)) from exc
        async with self._workspace_locks[task_id]:
            task = await asyncio.to_thread(self._ledger.get, task_id)
            if task.state in {
                TaskState.COMPLETED,
                TaskState.FAILED,
                TaskState.CANCELLED,
            }:
                raise RuntimeError("task is not accepting messages")
            await self._expire_sleeping_locked(task)
            existing = await asyncio.to_thread(
                self._ledger.get_task_message_receipt, task_id, message_id
            )
            if existing is not None:
                if existing.content != content:
                    raise RuntimeError("message id already belongs to another message")
                return existing
            accepted = MessageReceipt(
                id=message_id,
                content=content,
                status=MessageDeliveryStatus.ACCEPTED,
            )
            await asyncio.to_thread(
                self._ledger.save_task_message_receipt, task_id, accepted
            )
            await asyncio.to_thread(self._ledger.touch_workspace, task_id)
            if (
                await asyncio.to_thread(self._ledger.get, task_id)
            ).state is TaskState.SLEEPING:
                await asyncio.to_thread(self._ledger.queue_workspace_message, task_id)
            self._ensure_loop(task_id)
            return accepted

    async def expire_sleeping_workspace(self, task_id: str) -> None:
        async with self._workspace_locks[task_id]:
            task = await asyncio.to_thread(self._ledger.get, task_id)
            if task is not None:
                await self._expire_sleeping_locked(task)

    async def _expire_sleeping_locked(self, task: TaskRecord) -> None:
        last_activity = task.workspace_last_activity_at or task.updated_at
        if (
            task.state is TaskState.SLEEPING
            and not task.workspace_expired
            and datetime.now(UTC) - last_activity >= timedelta(days=7)
        ):
            await self._lifecycle.expire_workspace(task.id)
            await asyncio.to_thread(self._ledger.expire_workspace, task.id)

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
                reservation = await asyncio.to_thread(
                    self._ledger.get_reservation, task_id
                )
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
            await asyncio.to_thread(
                self._ledger.update_reservation,
                task_id,
                phase=ReservationPhase.RUNNING,
                condition=f"supervision error: {exc}",
            )

    async def _drive_running(self, task_id: str) -> None:
        task = await asyncio.to_thread(self._ledger.get, task_id)
        if task is None:
            return
        if task.state is TaskState.QUEUED:
            await asyncio.to_thread(
                self._ledger.update_reservation,
                task_id,
                phase=ReservationPhase.RUNNING,
                task_state=TaskState.RUNNING,
            )
        try:
            connection = await self._lifecycle.connect(task_id)
        except ModalLifecycleError as exc:
            await asyncio.to_thread(
                self._ledger.update_reservation,
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
            try:
                await self._sync_events(
                    task_id, connection, supervision.conversation_id
                )
            except httpx.HTTPError:
                pass
        execution = await client.get_execution(supervision.execution_id)
        if supervision.cancel_requested:
            await self._cancel_execution(task_id, connection, supervision, client)
            execution = await client.get_execution(supervision.execution_id)
        if execution.phase in {
            TaskExecutionPhase.COMPLETED,
            TaskExecutionPhase.FAILED,
        }:
            archive = await asyncio.to_thread(self._ledger.get_task_result, task_id)
            if archive is not None and archive.execution_id == execution.execution_id:
                pending = await asyncio.to_thread(
                    self._ledger.list_accepted_task_messages, task_id
                )
                if pending:
                    await self._start_followup(task_id, client, pending[0])
                elif task.state is TaskState.IDLE:
                    last_activity = task.workspace_last_activity_at or task.updated_at
                    if datetime.now(UTC) - last_activity >= timedelta(minutes=45):
                        await self._sleep_workspace(task_id)
                return
            await asyncio.to_thread(
                self._ledger.update_reservation,
                task_id,
                phase=ReservationPhase.FINALIZING,
                task_state=TaskState.FINALIZING,
            )

    async def _ensure_execution_started(
        self, task_id: str, client: TaskSupervisorClient
    ) -> SupervisionRecord | None:
        task = await asyncio.to_thread(self._ledger.get, task_id)
        if task is None:
            return None
        supervision = await asyncio.to_thread(self._ledger.get_supervision, task_id)
        if supervision is None or supervision.execution_id == task_id:
            supervision = await self._start_execution(task_id, task, client)
        elif supervision.execution_id == supervision.start_key:
            receipt = await asyncio.to_thread(
                self._ledger.get_task_message_receipt,
                task_id,
                supervision.start_key.partition(":")[2],
            )
            if receipt is not None:
                await self._start_followup(task_id, client, receipt)
                supervision = await asyncio.to_thread(
                    self._ledger.get_supervision, task_id
                )
        elif supervision is not None:
            try:
                await client.get_execution(supervision.execution_id)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != 404:
                    raise
                pending = await asyncio.to_thread(
                    self._ledger.list_accepted_task_messages, task_id
                )
                if not pending:
                    return None
                await self._start_followup(task_id, client, pending[0])
                supervision = await asyncio.to_thread(
                    self._ledger.get_supervision, task_id
                )
        if supervision is None:
            return None
        return await self._refresh_supervision(task_id, client, supervision)

    async def _start_followup(
        self, task_id: str, client: TaskSupervisorClient, receipt: MessageReceipt
    ) -> None:
        task = await asyncio.to_thread(self._ledger.get, task_id)
        supervision = await asyncio.to_thread(self._ledger.get_supervision, task_id)
        if task is None or supervision is None:
            return
        try:
            github_token = await self._fresh_github_token(task)
        except RepositoryAccessError as exc:
            failed = receipt.model_copy(
                update={
                    "status": MessageDeliveryStatus.FAILED,
                    "detail": str(exc),
                    "updated_at": datetime.now(UTC),
                }
            )
            await asyncio.to_thread(
                self._ledger.save_task_message_receipt, task_id, failed
            )
            await asyncio.to_thread(
                self._ledger.update_reservation,
                task_id,
                phase=ReservationPhase.RUNNING,
                condition=str(exc),
            )
            return
        start_key = f"{task_id}:{receipt.id}"
        if supervision.start_key != start_key:
            supervision = await asyncio.to_thread(
                self._ledger.update_supervision,
                task_id,
                execution_id=start_key,
                start_key=start_key,
            )
        request = StartTaskExecutionRequest(
            task_id=task_id,
            repository=task.repository,
            prompt=receipt.content,
            base_ref=task.base_ref,
            base_sha=task.base_sha,
            task_branch=supervision.task_branch,
            start_key=start_key,
            deadline_at=datetime.now(UTC) + DEFAULT_TASK_DEADLINE,
            model=task.model,
        )
        record, _ = await client.start(request, github_token=github_token)
        delivered = receipt.model_copy(
            update={
                "status": MessageDeliveryStatus.DELIVERED,
                "updated_at": datetime.now(UTC),
            }
        )
        await asyncio.to_thread(
            self._ledger.save_task_message_receipt, task_id, delivered
        )
        await asyncio.to_thread(
            self._ledger.update_supervision,
            task_id,
            execution_id=record.execution_id,
            conversation_id=record.conversation_id or supervision.conversation_id,
        )
        await asyncio.to_thread(
            self._ledger.finish_task, task_id, state=TaskState.RUNNING
        )

    async def _sleep_workspace(self, task_id: str) -> None:
        async with self._workspace_locks[task_id]:
            if not (await asyncio.to_thread(self._ledger.try_mark_sleeping, task_id)):
                return
            try:
                await self._lifecycle.sync(task_id)
                snapshot = await self._lifecycle.terminate(task_id)
                if snapshot.state is not SandboxProviderState.STOPPED:
                    raise ModalLifecycleError("sandbox sleep was not confirmed")
            except Exception:
                if (
                    await asyncio.to_thread(self._ledger.get, task_id)
                ).state is TaskState.SLEEPING:
                    await asyncio.to_thread(
                        self._ledger.finish_task, task_id, state=TaskState.IDLE
                    )
                raise
            await asyncio.to_thread(self._ledger.release_reservation, task_id)

    async def _fresh_github_token(self, task: TaskRecord) -> str | None:
        if task.owner_id is None or task.repository is None:
            return None
        if self._repository_authorization is None:
            raise RuntimeError("GitHub repository authorization unavailable")
        credential = await asyncio.to_thread(
            self._repository_authorization.credential,
            task.owner_id,
            task.repository,
            task.base_ref or "",
        )
        return credential.token

    async def _start_execution(
        self, task_id: str, task: TaskRecord, client: TaskSupervisorClient
    ) -> SupervisionRecord | None:
        reservation = await asyncio.to_thread(self._ledger.get_reservation, task_id)
        duration = (
            timedelta(minutes=45)
            if task.owner_id and task.repository
            else DEFAULT_TASK_DEADLINE
        )
        deadline_at = (
            reservation.reserved_at + duration
            if reservation is not None
            else datetime.now(UTC) + duration
        )
        task_branch = f"{TASK_BRANCH_PREFIX}/{task_id}"
        await asyncio.to_thread(
            self._ledger.begin_supervision,
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
            base_sha=task.base_sha,
            task_branch=task_branch,
            start_key=task_id,
            deadline_at=deadline_at,
            model=task.model,
        )
        try:
            record, _ = await client.start(
                request, github_token=await self._fresh_github_token(task)
            )
        except RepositoryAccessError as exc:
            await asyncio.to_thread(
                self._ledger.finish_task,
                task_id,
                state=TaskState.FAILED,
                outcome_detail=str(exc),
            )
            await asyncio.to_thread(
                self._ledger.update_reservation,
                task_id,
                phase=ReservationPhase.TERMINATION_PENDING,
                condition=str(exc),
            )
            return None
        except httpx.HTTPError as exc:
            await asyncio.to_thread(
                self._ledger.update_reservation,
                task_id,
                phase=ReservationPhase.RUNNING,
                condition=f"execution start failed: {exc}",
            )
            return await asyncio.to_thread(self._ledger.get_supervision, task_id)
        await asyncio.to_thread(
            self._ledger.update_supervision,
            task_id,
            execution_id=record.execution_id,
            conversation_id=record.conversation_id,
        )
        if task.base_sha is None and record.base_ref:
            manifest = await _try_manifest(client, record.execution_id)
            if manifest is not None:
                await asyncio.to_thread(
                    self._ledger.record_base_sha, task_id, manifest.base_sha
                )
        return await asyncio.to_thread(self._ledger.get_supervision, task_id)

    async def _refresh_supervision(
        self,
        task_id: str,
        client: TaskSupervisorClient,
        supervision: SupervisionRecord,
    ) -> SupervisionRecord:
        try:
            execution = await client.get_execution(supervision.execution_id)
        except httpx.HTTPError:
            return supervision
        if (
            not execution.conversation_id
            or execution.conversation_id == supervision.conversation_id
        ):
            return supervision
        return await asyncio.to_thread(
            self._ledger.update_supervision,
            task_id,
            conversation_id=execution.conversation_id,
        )

    async def _sync_events(
        self, task_id: str, connection: object, conversation_id: str
    ) -> None:
        async with connection.http_client(timeout=30) as client:  # type: ignore[attr-defined]
            response = await client.get(f"/api/conversations/{conversation_id}/events")
        if response.status_code == 404:
            return
        response.raise_for_status()
        for payload in response.json():
            event = Event.model_validate(payload)
            event_json = event.model_dump_json()
            if self._storage_limits is not None:
                evidence = await asyncio.to_thread(
                    measure_task_evidence, self._ledger, task_id
                )
                event_json, _ = truncate_event_json(
                    event,
                    max_task_log_bytes=self._storage_limits.max_log_evidence_bytes,
                    current_log_bytes=evidence.log_bytes,
                )
            cursor = await asyncio.to_thread(
                self._ledger.copy_task_event,
                task_id=task_id,
                source_id=conversation_id,
                source_seq=event.seq,
                event=event,
                event_json=event_json,
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
        await asyncio.to_thread(
            self._ledger.update_reservation,
            task_id,
            phase=ReservationPhase.FINALIZING,
            task_state=TaskState.FINALIZING,
        )

    async def _finalize(self, task_id: str) -> None:
        async with self._settlement_locks[task_id]:
            await self._finalize_locked(task_id)

    async def _finalize_locked(self, task_id: str) -> None:
        task = await asyncio.to_thread(self._ledger.get, task_id)
        supervision = await asyncio.to_thread(self._ledger.get_supervision, task_id)
        if task is None or supervision is None:
            return
        if task.state in {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED}:
            await self._attempt_cleanup(task_id)
            return
        try:
            connection = await self._lifecycle.connect(task_id)
        except ModalLifecycleError:
            await asyncio.to_thread(
                self._ledger.update_supervision, task_id, tail_gap_possible=True
            )
            await asyncio.to_thread(
                self._ledger.finish_task,
                task_id,
                state=TaskState.FAILED,
                outcome_detail="sandbox lost before finalization completed",
            )
            await asyncio.to_thread(
                self._ledger.update_reservation,
                task_id,
                phase=ReservationPhase.TERMINATION_PENDING,
                condition="sandbox lost; cleanup pending",
            )
            return
        client = TaskSupervisorClient(connection)
        supervision = await self._refresh_supervision(task_id, client, supervision)
        if supervision.conversation_id:
            try:
                await self._sync_events(
                    task_id, connection, supervision.conversation_id
                )
            except httpx.HTTPError:
                await asyncio.to_thread(
                    self._ledger.update_supervision, task_id, tail_gap_possible=True
                )
        manifest = await _fetch_manifest_with_retries(
            client, supervision.execution_id, budget=DEFAULT_CLEANUP_BUDGET
        )
        if manifest is not None and self._storage_limits is not None:
            manifest, _ = truncate_manifest(
                manifest,
                max_bytes=self._storage_limits.max_artifact_bytes,
            )
        evidence_complete = manifest is not None
        evidence_detail = None if evidence_complete else "manifest archival incomplete"
        await asyncio.to_thread(
            self._ledger.archive_task_result,
            task_id=task_id,
            execution_id=supervision.execution_id,
            manifest=manifest,
            evidence_complete=evidence_complete,
            evidence_detail=evidence_detail,
        )
        terminal_state, outcome_detail, check_status = _terminal_from_manifest(
            task, manifest, supervision.cancel_requested
        )
        if terminal_state is not TaskState.CANCELLED:
            terminal_state = TaskState.IDLE
        await asyncio.to_thread(
            self._ledger.finish_task,
            task_id,
            state=terminal_state,
            outcome_detail=outcome_detail,
            check_status=check_status,
        )
        if terminal_state is TaskState.IDLE:
            await asyncio.to_thread(
                self._ledger.update_reservation,
                task_id,
                phase=ReservationPhase.RUNNING,
                task_state=TaskState.IDLE,
            )
            return
        await asyncio.to_thread(
            self._ledger.update_reservation,
            task_id,
            phase=ReservationPhase.TERMINATION_PENDING,
            condition=None,
        )

    async def _settle_messages(
        self, task_id: str, connection: object, supervision: SupervisionRecord
    ) -> None:
        if supervision.conversation_id is None:
            for receipt in await asyncio.to_thread(
                self._ledger.list_accepted_task_messages, task_id
            ):
                failed = receipt.model_copy(
                    update={
                        "status": MessageDeliveryStatus.FAILED,
                        "detail": "conversation unavailable before settlement",
                        "updated_at": datetime.now(UTC),
                    }
                )
                await asyncio.to_thread(
                    self._ledger.save_task_message_receipt, task_id, failed
                )
            return
        for receipt in await asyncio.to_thread(
            self._ledger.list_accepted_task_messages, task_id
        ):
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
            await asyncio.to_thread(
                self._ledger.save_task_message_receipt, task_id, settled
            )

    async def _attempt_cleanup(self, task_id: str) -> None:
        try:
            snapshot = await self._lifecycle.terminate(task_id)
        except ModalLifecycleError as exc:
            await asyncio.to_thread(
                self._ledger.update_reservation,
                task_id,
                phase=ReservationPhase.TERMINATION_PENDING,
                condition=f"termination unresolved: {exc}",
            )
            return
        if snapshot.state is SandboxProviderState.STOPPED:
            await asyncio.to_thread(
                self._ledger.release_reservation,
                task_id,
                cleanup_status="confirmed_absent",
            )
        else:
            await asyncio.to_thread(
                self._ledger.update_reservation,
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
