"""Orchestrate repository preparation, Pi, checks, and local evidence."""

from __future__ import annotations

import asyncio
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from gg.sdk import AgentError, ConversationStatus, PiAgentConfig
from gg.sdk.repository_profiles import RepositoryProfile, profiles_by_repository
from gg.sdk.task_execution import (
    AgentOutcome,
    CheckOutcome,
    CommandCapture,
    StartTaskExecutionRequest,
    TaskExecutionPhase,
    TaskExecutionRecord,
    TaskResultManifest,
)

from gg.server.config import Settings
from gg.server.conversation_service import ConversationService
from gg.server.task_supervisor.commands import run_bounded_command
from gg.server.task_supervisor.git_prep import (
    GitPrepError,
    checkout_task_branch,
    clone_repository,
    collect_git_evidence,
    resolve_base_sha,
    run_bootstrap,
)
from gg.server.task_supervisor.store import ExecutionStore, StartKeyConflictError

MAX_PATCH_BYTES = 512_000
DEFAULT_AGENT_TIMEOUT_SECONDS = 60 * 55


class TaskSupervisorService:
    """Sandbox-local supervisor with durable, idempotent execution startup."""

    def __init__(
        self,
        *,
        settings: Settings,
        conversation_service: ConversationService,
        store: ExecutionStore | None = None,
    ) -> None:
        self._settings = settings
        self._conversation_service = conversation_service
        self._store = store or ExecutionStore(settings.task_supervisor_dir)
        self._profiles = profiles_by_repository(settings.repository_profiles)
        self._github_token = settings.github_clone_token
        self._process_env = settings.process_env
        self._active: dict[str, asyncio.Task[None]] = {}
        self._started = False

    async def startup(self) -> None:
        if self._started:
            return
        self._started = True
        for record in self._store.list_non_terminal():
            detail = "supervisor ownership lost on process restart"
            await self._finalize_failure(
                record,
                detail=detail,
                agent_outcome=AgentOutcome.NOT_RUN,
                check_outcome=CheckOutcome.NOT_RUN,
                repository=record.repository,
                task_branch=record.task_branch,
                base_ref=record.base_ref,
            )
            self._stop_orphan_processes(record.execution_id)

    async def shutdown(self) -> None:
        tasks = list(self._active.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._active.clear()
        self._started = False

    async def start(
        self, request: StartTaskExecutionRequest
    ) -> tuple[TaskExecutionRecord, bool]:
        profile = self._require_profile(request.repository)
        if self._github_token is None:
            raise RuntimeError("github clone token is not configured")
        try:
            record, created = self._store.admit_or_get(
                start_key=request.start_key,
                task_id=request.task_id,
                repository=request.repository,
                task_branch=request.task_branch,
                base_ref=request.base_ref,
                deadline_at=request.deadline_at,
            )
        except StartKeyConflictError:
            raise
        if not created:
            return record, False
        if record.execution_id in self._active:
            return record, False
        task = asyncio.create_task(
            self._run_pipeline(request, profile, record),
            name=f"task-exec-{record.execution_id}",
        )
        self._active[record.execution_id] = task
        task.add_done_callback(
            lambda _: self._active.pop(record.execution_id, None)
        )
        return record, True

    def get_execution(self, execution_id: str) -> TaskExecutionRecord:
        return self._store.load_execution(execution_id)

    def get_manifest(self, execution_id: str) -> TaskResultManifest:
        return self._store.load_manifest(execution_id)

    def _require_profile(self, repository: str) -> RepositoryProfile:
        profile = self._profiles.get(repository)
        if profile is None:
            raise ValueError(f"no repository profile configured for {repository!r}")
        return profile

    async def _run_pipeline(
        self,
        request: StartTaskExecutionRequest,
        profile: RepositoryProfile,
        record: TaskExecutionRecord,
    ) -> None:
        repo_dir = self._settings.workspace_dir / "repos" / request.task_id
        base_ref = request.base_ref or profile.default_base_ref
        base_sha = ""
        bootstrap_capture: CommandCapture | None = None
        check_capture: CommandCapture | None = None
        conversation_id: str | None = None
        try:
            await self._update_phase(record, TaskExecutionPhase.PREPARING)
            clone_repository(
                repository=request.repository,
                destination=repo_dir,
                github_token=self._github_token,
                process_env=self._process_env,
            )
            base_sha = resolve_base_sha(repo_dir=repo_dir, base_ref=base_ref)
            checkout_task_branch(
                repo_dir=repo_dir, branch=request.task_branch, base_sha=base_sha
            )
            bootstrap_capture = await asyncio.to_thread(
                run_bootstrap,
                repo_dir=repo_dir,
                command=profile.bootstrap_command,
                timeout_seconds=self._remaining_seconds(request.deadline_at, minimum=30),
                max_output_bytes=profile.max_bootstrap_output_bytes,
                process_env=self._process_env,
            )
            if bootstrap_capture.exit_code not in (0, None):
                raise GitPrepError(
                    f"bootstrap failed with exit code {bootstrap_capture.exit_code}"
                )
            if bootstrap_capture.timed_out:
                raise TimeoutError("bootstrap timed out")

            await self._update_phase(record, TaskExecutionPhase.RUNNING_AGENT)
            conversation_id = str(uuid4())
            record = record.model_copy(update={"conversation_id": conversation_id})
            self._store.save_execution(record)
            agent_outcome = await self._run_agent(
                request=request,
                repo_dir=repo_dir,
                conversation_id=conversation_id,
            )
            head_sha, changed, patch, patch_truncated = collect_git_evidence(
                repo_dir=repo_dir,
                base_sha=base_sha,
                max_patch_bytes=MAX_PATCH_BYTES,
            )
            check_outcome = CheckOutcome.NOT_RUN
            if agent_outcome is AgentOutcome.SUCCEEDED and not changed:
                agent_outcome = AgentOutcome.NO_CHANGES
            elif agent_outcome is AgentOutcome.SUCCEEDED:
                await self._update_phase(record, TaskExecutionPhase.RUNNING_CHECKS)
                check_capture = await asyncio.to_thread(
                    run_bounded_command,
                    command=profile.check_command,
                    cwd=str(repo_dir),
                    timeout_seconds=self._remaining_seconds(
                        request.deadline_at, minimum=30
                    ),
                    max_output_bytes=profile.max_check_output_bytes,
                    process_env=self._process_env,
                )
                check_outcome = self._check_outcome(check_capture)

            manifest = TaskResultManifest(
                task_id=request.task_id,
                execution_id=record.execution_id,
                repository=request.repository,
                task_branch=request.task_branch,
                base_ref=base_ref,
                base_sha=base_sha,
                head_sha=head_sha,
                changed_files=changed,
                patch=patch,
                patch_truncated=patch_truncated,
                bootstrap=bootstrap_capture,
                check=check_capture,
                check_outcome=check_outcome,
                agent_outcome=agent_outcome,
                conversation_id=conversation_id,
                completed_at=datetime.now(UTC),
            )
            path = self._store.save_manifest(manifest)
            terminal = (
                TaskExecutionPhase.COMPLETED
                if agent_outcome is AgentOutcome.NO_CHANGES
                or (
                    agent_outcome is AgentOutcome.SUCCEEDED
                    and check_outcome is CheckOutcome.PASSED
                )
                else TaskExecutionPhase.FAILED
            )
            detail = None
            if agent_outcome is AgentOutcome.NO_CHANGES:
                detail = "no_changes"
            elif check_outcome is CheckOutcome.FAILED:
                detail = "checks_failed"
            elif agent_outcome is AgentOutcome.FAILED:
                detail = "agent_failed"
            await self._update_phase(
                record,
                terminal,
                manifest_path=str(path),
                outcome_detail=detail,
            )
        except TimeoutError as exc:
            await self._finalize_failure(
                record,
                detail=str(exc),
                agent_outcome=AgentOutcome.TIMEOUT,
                check_outcome=CheckOutcome.NOT_RUN,
                base_ref=base_ref,
                base_sha=base_sha or None,
                bootstrap=bootstrap_capture,
                check=check_capture,
                conversation_id=conversation_id,
                repository=request.repository,
                task_branch=request.task_branch,
            )
        except (GitPrepError, AgentError, RuntimeError, ValueError) as exc:
            await self._finalize_failure(
                record,
                detail=str(exc),
                agent_outcome=AgentOutcome.FAILED,
                check_outcome=CheckOutcome.NOT_RUN,
                base_ref=base_ref,
                base_sha=base_sha or None,
                bootstrap=bootstrap_capture,
                check=check_capture,
                conversation_id=conversation_id,
                repository=request.repository,
                task_branch=request.task_branch,
            )

    async def _run_agent(
        self,
        *,
        request: StartTaskExecutionRequest,
        repo_dir: Path,
        conversation_id: str,
    ) -> AgentOutcome:
        if "GH_TOKEN" in self._process_env:
            raise RuntimeError("GH_TOKEN must not be present in Pi environment")
        meta = self._conversation_service.create(
            working_dir=repo_dir,
            conversation_id=conversation_id,
            agent=PiAgentConfig(),
        )
        _ = meta
        self._conversation_service.send_message(conversation_id, request.prompt)
        timeout = min(
            DEFAULT_AGENT_TIMEOUT_SECONDS,
            self._remaining_seconds(request.deadline_at, minimum=30),
        )
        try:
            record = await asyncio.wait_for(
                self._conversation_service.run(conversation_id),
                timeout=timeout,
            )
        except TimeoutError:
            await self._conversation_service.cancel(conversation_id)
            return AgentOutcome.TIMEOUT
        if record.status is ConversationStatus.CANCELLED:
            return AgentOutcome.CANCELLED
        if record.status is ConversationStatus.ERROR:
            return AgentOutcome.FAILED
        if record.status is ConversationStatus.FINISHED:
            return AgentOutcome.SUCCEEDED
        return AgentOutcome.FAILED

    async def _finalize_failure(
        self,
        record: TaskExecutionRecord,
        *,
        detail: str,
        agent_outcome: AgentOutcome,
        check_outcome: CheckOutcome,
        repository: str | None = None,
        task_branch: str | None = None,
        base_ref: str | None = None,
        base_sha: str | None = None,
        bootstrap: CommandCapture | None = None,
        check: CommandCapture | None = None,
        conversation_id: str | None = None,
    ) -> None:
        manifest = TaskResultManifest(
            task_id=record.task_id,
            execution_id=record.execution_id,
            repository=repository or record.repository,
            task_branch=task_branch or record.task_branch,
            base_ref=base_ref or record.base_ref or "unknown",
            base_sha=base_sha or "unknown",
            bootstrap=bootstrap,
            check=check,
            check_outcome=check_outcome,
            agent_outcome=agent_outcome,
            conversation_id=conversation_id or record.conversation_id,
            outcome_detail=detail,
            completed_at=datetime.now(UTC),
        )
        path = self._store.save_manifest(manifest)
        await self._update_phase(
            record,
            TaskExecutionPhase.FAILED,
            manifest_path=str(path),
            outcome_detail=detail,
        )

    async def _update_phase(
        self,
        record: TaskExecutionRecord,
        phase: TaskExecutionPhase,
        *,
        manifest_path: str | None = None,
        outcome_detail: str | None = None,
    ) -> None:
        updated = record.model_copy(
            update={
                "phase": phase,
                "manifest_path": manifest_path or record.manifest_path,
                "outcome_detail": outcome_detail or record.outcome_detail,
                "updated_at": datetime.now(UTC),
            }
        )
        self._store.save_execution(updated)

    @staticmethod
    def _remaining_seconds(deadline_at: datetime, *, minimum: float) -> float:
        remaining = (deadline_at - datetime.now(UTC)).total_seconds()
        return max(minimum, remaining)

    @staticmethod
    def _check_outcome(capture: CommandCapture) -> CheckOutcome:
        if capture.timed_out:
            return CheckOutcome.TIMEOUT
        if capture.exit_code == 0:
            return CheckOutcome.PASSED
        return CheckOutcome.FAILED

    @staticmethod
    def _stop_orphan_processes(execution_id: str) -> None:
        # Best-effort cleanup for orphaned agent processes after restart.
        try:
            subprocess.run(
                ["pkill", "-f", execution_id],
                capture_output=True,
                check=False,
            )
        except OSError:
            return


__all__ = ["TaskSupervisorService"]
