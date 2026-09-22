from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport

from gg.runtime import RuntimeSettings, TaskLedger, create_app
from gg.runtime.backup import backup_sqlite_online
from gg.runtime.scheduler import DeploymentLock, DispatchLockError
from gg.runtime.storage import StorageLimits, admission_pressure, run_retention_pass
from gg.runtime.task_service import StoragePressureError, TaskService
from gg.sdk.domain import Event, EventKind
from gg.sdk.tasks import CreateTaskRequest, TaskState


_AUTH = {"X-API-Key": "control-secret"}


def _settings(tmp_path: Path, **overrides) -> RuntimeSettings:
    base = {
        "api_key": "control-secret",
        "image": "test-image:dev",
        "task_db_path": str(tmp_path / "tasks.sqlite"),
        "repository_allowlist": ("owner/allowed",),
        "max_total_evidence_bytes": 4096,
        "min_free_disk_bytes": 0,
    }
    base.update(overrides)
    return RuntimeSettings(**base)


@pytest.mark.anyio
async def test_runtime_ready_reports_scheduler_ownership(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://runtime"
    ) as client:
        async with app.router.lifespan_context(app):
            response = await client.get("/ready", headers=_AUTH)

    assert response.status_code == 200
    body = response.json()
    assert body["database_available"] is True
    assert body["dispatch_owner"] is True
    assert body["status"] == "ready"


@pytest.mark.anyio
async def test_health_is_public_and_tasks_require_auth(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://runtime"
    ) as client:
        async with app.router.lifespan_context(app):
            health = await client.get("/health")
            denied = await client.get("/tasks")

    assert health.status_code == 200
    assert denied.status_code == 401


def test_storage_pressure_blocks_submission(tmp_path: Path) -> None:
    with TaskLedger(db_path=str(tmp_path / "tasks.sqlite")) as ledger:
        ledger.submit(
            idempotency_key="big",
            repository="owner/allowed",
            prompt="x",
            base_ref=None,
            retry_of=None,
        )
        ledger.copy_task_event(
            task_id=ledger.list()[0].id,
            source_id="conv",
            source_seq=1,
            event=Event(seq=1, kind=EventKind.STATUS, payload={"log": "x" * 8000}),
        )
        settings = _settings(tmp_path, max_total_evidence_bytes=1024)
        service = TaskService(ledger=ledger, settings=settings)
        with pytest.raises(StoragePressureError):
            service.submit(
                CreateTaskRequest(
                    repository="owner/allowed",
                    base_ref="main",
                    prompt="another",
                    idempotency_key="k2",
                )
            )


def test_retention_expires_terminal_payload_but_keeps_idempotency(
    tmp_path: Path,
) -> None:
    with TaskLedger(db_path=str(tmp_path / "tasks.sqlite")) as ledger:
        record, _ = ledger.submit(
            idempotency_key="keep-me",
            repository="owner/allowed",
            prompt="work",
            base_ref=None,
            retry_of=None,
        )
        ledger.copy_task_event(
            task_id=record.id,
            source_id="conv",
            source_seq=1,
            event=Event(seq=1, kind=EventKind.STATUS, payload={"detail": "log"}),
        )
        ledger.finish_task(record.id, state=TaskState.COMPLETED)
        old = datetime.now(UTC) - timedelta(days=8)
        assert ledger._conn is not None
        with ledger._lock:
            ledger._conn.execute(
                "UPDATE tasks SET updated_at = ? WHERE id = ?",
                (old.isoformat(), record.id),
            )
        limits = StorageLimits(
            terminal_retention=timedelta(days=7),
            tombstone_retention=timedelta(days=90),
            max_log_evidence_bytes=1024,
            max_artifact_bytes=1024,
            max_total_evidence_bytes=1024 * 1024,
            min_free_disk_bytes=0,
            evidence_dir=None,
        )
        expired, _ = run_retention_pass(ledger, limits)
        assert expired == 1
        assert ledger.count_task_log_bytes(record.id) == 0
        replay, created = ledger.submit(
            idempotency_key="keep-me",
            repository="owner/allowed",
            prompt="work",
            base_ref=None,
            retry_of=None,
        )
        assert created is False
        assert replay.payload_expired is True


def test_online_backup_creates_consistent_sqlite_copy(tmp_path: Path) -> None:
    source = tmp_path / "tasks.sqlite"
    backup_path = tmp_path / "backup" / "tasks.sqlite"
    with TaskLedger(db_path=str(source)) as ledger:
        ledger.submit(
            idempotency_key="backup",
            repository="owner/allowed",
            prompt="x",
            base_ref=None,
            retry_of=None,
        )
        backup_sqlite_online(ledger=ledger, destination=backup_path)
    with TaskLedger(db_path=str(backup_path)) as restored:
        assert len(restored.list()) == 1


def test_second_process_cannot_take_dispatch_lock(tmp_path: Path) -> None:
    lock_path = str(tmp_path / "dispatch.lock")
    first = DeploymentLock(lock_path)
    second = DeploymentLock(lock_path)
    first.acquire()
    try:
        with pytest.raises(DispatchLockError):
            second.acquire()
    finally:
        first.release()


def test_admission_pressure_uses_configured_free_disk_floor(tmp_path: Path) -> None:
    with TaskLedger(db_path=str(tmp_path / "tasks.sqlite")) as ledger:
        limits = StorageLimits(
            terminal_retention=timedelta(days=7),
            tombstone_retention=timedelta(days=90),
            max_log_evidence_bytes=1024,
            max_artifact_bytes=1024,
            max_total_evidence_bytes=10_000_000,
            min_free_disk_bytes=10**18,
            evidence_dir=None,
        )
        pressure = admission_pressure(
            ledger, limits, db_path=str(tmp_path / "tasks.sqlite")
        )
        assert pressure.blocked is True
