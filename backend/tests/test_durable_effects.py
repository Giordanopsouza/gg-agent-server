"""Commit failure and lost-response injection at real runtime effect boundaries."""

import shutil
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import HTTPException

from gg.runtime.checkpoints import CheckpointCoordinator
from gg.runtime.config import RuntimeSettings
from gg.runtime.ledger import TaskLedger
from gg.runtime.modal_sandbox import AmbiguousProviderStateError, ModalSandboxLifecycle
from gg.runtime.scheduler import TaskScheduler
from gg.runtime.sqlite_db import SQLiteDB, initialize
from gg.runtime.task_supervision.manager import TaskSupervisionManager
from gg.sdk.task_execution import TaskExecutionPhase


@pytest.fixture
def state(tmp_path):
    initialize(tmp_path / "db")
    flags = {"fail": False, "calls": 0}

    async def commit():
        flags["calls"] += 1
        if flags["fail"]:
            raise OSError("private commit failure")
        flags["saved"] = checkpoints.snapshot.read_bytes()

    db = SQLiteDB(tmp_path / "db")
    checkpoints = CheckpointCoordinator(db, tmp_path / "snapshot", commit)
    ledger = TaskLedger(db, checkpoints)
    task, _ = ledger.submit(
        idempotency_key="task",
        repository=None,
        prompt="hello",
        base_ref=None,
        retry_of=None,
    )
    ledger.reserve_next(capacity=1)
    yield ledger, checkpoints, flags, task
    db.close()


class Provider:
    def __init__(self, checkpoints, flags):
        self.checkpoints = checkpoints
        self.flags = flags
        self.calls = 0
        self.handles = []
        self.lost = False

    async def create(self, **kwargs):
        assert self.checkpoints.confirmed_revision >= self.checkpoints.db.revision
        self.calls += 1
        handle = SimpleNamespace(object_id="sb-1", tags=kwargs["tags"])
        self.handles.append(handle)
        if self.lost:
            raise ConnectionError("lost response")
        return handle

    async def find(self, *, tags):
        return [h for h in self.handles if h.tags == tags]

    async def from_id(self, provider_id):
        return next(h for h in self.handles if h.object_id == provider_id)

    async def poll(self, handle):
        return None

    async def wait_until_ready(self, handle, **kwargs):
        pass


@pytest.mark.anyio
async def test_creation_barrier_and_lost_response_reuse_identity(
    state,
):
    ledger, checkpoints, flags, task = state
    provider = Provider(checkpoints, flags)
    lifecycle = ModalSandboxLifecycle(
        ledger=ledger, provider=provider, deployment="test"
    )
    await ledger.ensure_durable()
    # Failure specifically after persisting creation intent, before provider call.
    original = ledger.begin_sandbox_creation

    def begin(**kwargs):
        result = original(**kwargs)
        flags["fail"] = True
        return result

    ledger.begin_sandbox_creation = begin
    with pytest.raises(HTTPException) as error:
        await lifecycle.create(task.id)
    assert error.value.status_code == 503 and provider.calls == 0
    intent = ledger.get_sandbox_creation(task.id)
    assert intent and intent.provider_id is None
    ledger.begin_sandbox_creation = original
    flags["fail"] = False
    provider.lost = True
    with pytest.raises(AmbiguousProviderStateError):
        await lifecycle.create(task.id)
    assert provider.calls == 1
    snapshot = await lifecycle.create(task.id)
    assert snapshot.provider_id == "sb-1" and provider.calls == 1
    assert ledger.get_sandbox_creation(task.id).sandbox_name == intent.sandbox_name


class Client:
    def __init__(self, checkpoints):
        self.checkpoints = checkpoints
        self.starts = []
        self.executions = {}
        self.lost = False

    async def start(self, request, **kwargs):
        assert self.checkpoints.confirmed_revision >= self.checkpoints.db.revision
        self.starts.append(request.start_key)
        record = self.executions.setdefault(
            request.start_key,
            SimpleNamespace(
                execution_id="execution-" + request.start_key,
                conversation_id="conversation",
                base_ref=None,
                phase=TaskExecutionPhase.RUNNING_AGENT,
            ),
        )
        if self.lost:
            raise ConnectionError("response lost")
        return record, True

    async def get_execution(self, execution_id):
        return next(
            r for r in self.executions.values() if r.execution_id == execution_id
        )


@pytest.mark.anyio
async def test_execution_intent_commit_failure_restore_and_lost_response(
    state, tmp_path
):
    ledger, checkpoints, flags, task = state
    manager = TaskSupervisionManager(
        ledger=ledger, lifecycle=object(), settings=RuntimeSettings(api_key="operator")
    )
    client = Client(checkpoints)
    flags["fail"] = True
    with pytest.raises(HTTPException):
        await manager._start_execution(task.id, task, client)
    assert client.starts == [] and ledger.get_supervision(task.id).start_key == task.id
    flags["fail"] = False
    await ledger.ensure_durable()
    # Fresh process restores the persisted execution identity.
    shutil.copyfile(checkpoints.snapshot, tmp_path / "recovered")

    async def commit():
        pass

    with SQLiteDB(tmp_path / "recovered") as db:
        restored_checkpoints = CheckpointCoordinator(
            db, tmp_path / "second.snapshot", commit
        )
        restored = TaskLedger(db, restored_checkpoints)
        manager = TaskSupervisionManager(
            ledger=restored,
            lifecycle=object(),
            settings=RuntimeSettings(api_key="operator"),
        )
        client = Client(restored_checkpoints)
        client.lost = True
        with pytest.raises(ConnectionError):
            await manager._ensure_execution_started(task.id, client)
        client.lost = False
        result = await manager._ensure_execution_started(task.id, client)
        assert result.execution_id == "execution-" + task.id
        assert client.starts == [task.id, task.id] and len(client.executions) == 1


@pytest.mark.anyio
async def test_message_intent_blocks_delivery_and_retry_uses_same_key(state):
    ledger, checkpoints, flags, task = state
    ledger.begin_supervision(
        task_id=task.id,
        execution_id="initial",
        task_branch="gg/task/" + task.id,
        start_key=task.id,
    )
    manager = TaskSupervisionManager(
        ledger=ledger, lifecycle=object(), settings=RuntimeSettings(api_key="operator")
    )
    # Prevent background work; exercise the explicit delivery boundary below.
    manager._ensure_loop = lambda _: None
    flags["fail"] = True
    with pytest.raises(HTTPException):
        await manager.send_message(task.id, message_id="message", content="follow up")
    client = Client(checkpoints)
    flags["fail"] = False
    receipt = await manager.send_message(
        task.id, message_id="message", content="follow up"
    )
    flags["fail"] = True
    with pytest.raises(HTTPException):
        await manager._start_followup(task.id, client, receipt)
    assert client.starts == []
    flags["fail"] = False
    client.lost = True
    with pytest.raises(ConnectionError):
        await manager._start_followup(task.id, client, receipt)
    client.lost = False
    await manager._start_followup(task.id, client, receipt)
    assert client.starts == [task.id + ":message"] * 2 and len(client.executions) == 1
    assert (
        ledger.get_task_message_receipt(task.id, "message").status.value
        == "delivered_to_pi"
    )


@pytest.mark.anyio
async def test_scheduler_blocks_capacity_and_recovers(state, tmp_path):
    ledger, checkpoints, flags, task = state
    provider = Provider(checkpoints, flags)
    lifecycle = ModalSandboxLifecycle(
        ledger=ledger, provider=provider, deployment="test"
    )
    scheduler = TaskScheduler(
        ledger=ledger,
        lifecycle=lifecycle,
        capacity=1,
        lock_path=str(tmp_path / "scheduler.lock"),
        admission_enabled=True,
    )
    flags["fail"] = True
    with pytest.raises(HTTPException):
        await scheduler.dispatch_once()
    assert provider.calls == 0
    assert scheduler.status().blocked_reason == "state persistence unavailable"
    flags["fail"] = False
    await scheduler.dispatch_once()
    assert provider.calls == 1 and scheduler.status().reconciled


@pytest.mark.anyio
async def test_publication_commit_blocks_push_and_pr_then_reconciles_lost_response(
    state, tmp_path
):
    from test_publication import (
        FakeGitHub,
        _edit,
        _prepared_repo,
        _publisher,
        _request,
        _run,
    )

    from gg.sdk.publication import PublicationState
    from gg.sdk.task_execution import CheckOutcome

    ledger, checkpoints, flags, task = state
    work, origin, base_sha = _prepared_repo(tmp_path)
    request = _request(task.id, check_outcome=CheckOutcome.NOT_RUN).model_copy(
        update={"base_sha": base_sha}
    )
    _edit(work, request.task_branch)
    github = FakeGitHub(ledger=ledger, task_id=task.id)
    publisher = _publisher(ledger, github)
    flags["fail"] = True
    with pytest.raises(HTTPException):
        await publisher.publish(request, repo_dir=work)
    assert github.create_calls == 0
    assert (
        _run(
            ["git", "ls-remote", str(origin), "refs/heads/" + request.task_branch],
            cwd=work,
        )
        == ""
    )
    flags["fail"] = False
    github.timeout_after_create = True
    recovered = await publisher.publish(request, repo_dir=work)
    assert github.create_calls == 1
    record = await publisher.publish(request, repo_dir=work)
    assert record.state is PublicationState.PUBLISHED and github.create_calls == 1
    assert recovered.pr_number == record.pr_number
    assert ledger.get_publication(task.id).task_marker == request.task_marker


@pytest.mark.anyio
async def test_write_token_is_authorized_only_after_publication_intent_commit(state):
    ledger, checkpoints, flags, task = state
    task = task.model_copy(
        update={"repository": "owner/repo", "base_ref": "main", "owner_id": UUID(int=1)}
    )
    manager = TaskSupervisionManager(
        ledger=ledger, lifecycle=object(), settings=RuntimeSettings(api_key="operator")
    )
    client = Client(checkpoints)

    async def token(_):
        return "scoped-token"

    manager._fresh_github_token = token
    flags["fail"] = True
    with pytest.raises(HTTPException):
        await manager._start_execution(task.id, task, client)
    intent = ledger.get_publication(task.id)
    assert (
        intent.repository == "owner/repo" and intent.task_branch == "gg/task/" + task.id
    )
    assert intent.task_marker == task.id and client.starts == []
    flags["fail"] = False
    await manager._start_execution(task.id, task, client)
    assert client.starts == [task.id]


@pytest.mark.anyio
async def test_crash_after_provider_effect_recovers_from_confirmed_intent(
    state, tmp_path
):
    ledger, checkpoints, flags, task = state
    provider = Provider(checkpoints, flags)
    lifecycle = ModalSandboxLifecycle(
        ledger=ledger, provider=provider, deployment="test"
    )
    create = provider.create

    async def fail_after_create(**kwargs):
        result = await create(**kwargs)
        flags["fail"] = True
        return result

    provider.create = fail_after_create
    with pytest.raises(HTTPException):
        await lifecycle.create(task.id)
    assert (
        provider.calls == 1
        and ledger.get_sandbox_creation(task.id).provider_id == "sb-1"
    )
    recovered_path = tmp_path / "restored-last-commit"
    recovered_path.write_bytes(flags["saved"])

    async def commit():
        pass

    with SQLiteDB(recovered_path) as db:
        restored = TaskLedger(
            db, CheckpointCoordinator(db, tmp_path / "restored.snapshot", commit)
        )
        assert restored.get_sandbox_creation(task.id).provider_id is None
        lifecycle = ModalSandboxLifecycle(
            ledger=restored, provider=provider, deployment="test"
        )
        snapshot = await lifecycle.create(task.id)
        assert snapshot.provider_id == "sb-1" and provider.calls == 1


@pytest.mark.anyio
async def test_startup_reconciles_reserved_provider_before_new_admission(
    state, tmp_path
):
    ledger, checkpoints, flags, task = state
    provider = Provider(checkpoints, flags)
    lifecycle = ModalSandboxLifecycle(
        ledger=ledger, provider=provider, deployment="test"
    )
    await lifecycle.create(task.id)
    queued, _ = ledger.submit(
        idempotency_key="second",
        repository=None,
        prompt="hello",
        base_ref=None,
        retry_of=None,
    )
    scheduler = TaskScheduler(
        ledger=ledger,
        lifecycle=lifecycle,
        capacity=1,
        lock_path=str(tmp_path / "startup.lock"),
        admission_enabled=False,
    )
    await scheduler.start()
    try:
        assert scheduler.status().reconciled
        assert ledger.get(task.id).state.value == "running"
        assert ledger.get(queued.id).state.value == "queued"
        assert ledger.get_sandbox_creation(task.id).provider_id == "sb-1"
        assert provider.calls == 1
    finally:
        # No production detach is needed for this in-memory provider.
        async def detach(_):
            pass

        provider.detach = detach
        await scheduler.stop()
