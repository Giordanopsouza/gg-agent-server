"""Regression checks for history, authentication, and event-loop responsiveness."""

from __future__ import annotations

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from uuid import UUID

import httpx
import pytest
from cryptography.fernet import Fernet
from joserfc import jwk, jwt
from sqlalchemy import text
from test_support.postgres_ledger import new_ledger

from gg.runtime.config import RuntimeSettings
from gg.runtime.scheduler import TaskScheduler
from gg.runtime.web_auth import SupabaseAuth
from gg.sdk.task_execution import AgentOutcome, TaskResultManifest
from gg.sdk.tasks import TaskState


USER = "d23bfe09-a12b-49c5-845f-315fc9ec10d6"
SESSION = "75945e5b-9b85-4167-8dc7-ae7ce12276a3"


def _provider():
    key = jwk.ECKey.generate_key("P-256", auto_kid=True)
    state = {"keys": [key.as_dict(private=False)], "jwks": 0, "users": 0}

    async def respond(request):
        if request.url.path.endswith("jwks.json"):
            state["jwks"] += 1
            await asyncio.sleep(0.01)
            return httpx.Response(200, json={"keys": state["keys"]})
        state["users"] += 1
        return httpx.Response(200, json={"id": USER, "email": "user@example.com"})

    provider = SupabaseAuth(
        RuntimeSettings(
            api_key="operator",
            supabase_url="https://project.supabase.co",
            supabase_publishable_key="publishable-key",
            web_origin="https://app.example",
            web_cookie_key=Fernet.generate_key().decode(),
        ),
        transport=httpx.MockTransport(respond),
    )
    return provider, key, state


def _token(key, **extra):
    return jwt.encode(
        {"alg": "ES256", "kid": key.kid},
        {
            "iss": "https://project.supabase.co/auth/v1",
            "aud": "authenticated",
            "role": "authenticated",
            "sub": USER,
            "session_id": SESSION,
            "exp": int(time.time()) + 300,
            **extra,
        },
        key,
        algorithms=["ES256"],
    )


@pytest.mark.anyio
async def test_parallel_auth_reuses_keys_and_client_but_checks_each_user():
    provider, key, state = _provider()
    try:
        client = provider._client()
        users = await asyncio.gather(
            *(provider.verified_user(_token(key)) for _ in range(12))
        )
        assert all(user["id"] == USER for user in users)
        assert state["jwks"] == 1
        assert state["users"] == 12
        assert provider._client() is client
    finally:
        await provider.close()
    assert client.is_closed


@pytest.mark.anyio
async def test_cached_keys_expire_and_new_signing_key_triggers_refresh():
    provider, key, state = _provider()
    try:
        await provider.verified_user(_token(key))
        new_key = jwk.ECKey.generate_key("P-256", auto_kid=True)
        state["keys"] = [new_key.as_dict(private=False)]
        provider._jwks_fetched_at -= 11
        await provider.verified_user(_token(new_key))
        assert state["jwks"] == 2
        provider._jwks_fetched_at -= 601
        await provider.verified_user(_token(new_key))
        assert state["jwks"] == 3
        with pytest.raises(ValueError):
            await provider.verified_user(_token(new_key, exp=1))
        assert state["users"] == 3
    finally:
        await provider.close()


@pytest.mark.anyio
async def test_bad_tokens_cannot_force_unbounded_key_refresh():
    provider, key, state = _provider()
    try:
        await provider.verified_user(_token(key))
        foreign_key = jwk.ECKey.generate_key("P-256", auto_kid=True)
        for _ in range(5):
            with pytest.raises(Exception):
                await provider.verified_user(_token(foreign_key))
        assert state["jwks"] == 1
        assert state["users"] == 1
    finally:
        await provider.close()


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

        def list(self):
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
            task.id,
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
        # Dict rows on raw ledger connections must not leak into SQLAlchemy's
        # shared engine, used by auth sessions and credential services.
        with ledger.engine.connect() as connection:
            assert connection.execute(text("select 1")).scalar_one() == 1


def test_history_reads_do_not_wait_for_the_writer_lock():
    with new_ledger() as ledger:
        with ThreadPoolExecutor(max_workers=1) as worker:
            with ledger._lock:
                assert worker.submit(ledger.list).result(timeout=2) == []


def test_single_connection_configuration_keeps_working():
    ledger = new_ledger()
    ledger._database = replace(ledger._database, max_size=1)
    with ledger:
        assert ledger.list() == []


@pytest.mark.anyio
async def test_cached_signing_keys_still_check_session_revocation():
    from fastapi import HTTPException

    from gg.runtime.web_auth import authenticated_web_user

    class Sessions:
        revoked = False

        def active(self, user_id, session_id):
            assert (user_id, session_id) == (USER, SESSION)
            return not self.revoked

    provider, key, state = _provider()
    sessions = Sessions()
    cookie = provider.seal({"access": _token(key), "refresh": "unused"})
    try:
        await authenticated_web_user(provider, sessions, cookie)
        sessions.revoked = True
        with pytest.raises(HTTPException) as error:
            await authenticated_web_user(provider, sessions, cookie)
        assert error.value.status_code == 401
        assert state["jwks"] == 1
        assert state["users"] == 2
    finally:
        await provider.close()


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

        def list(self):
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
