from __future__ import annotations

import os

import pytest

from gg.runtime.config import (
    DEFAULT_MODAL_APP_NAME,
    DEFAULT_MODAL_DEPLOYMENT,
    DEFAULT_MODAL_IMAGE_NAME,
)
from gg.runtime.ledger import SandboxProviderState, TaskLedger
from gg.runtime.modal_sandbox import ModalProvider, ModalSandboxLifecycle
from gg.runtime.sqlite_db import SQLiteDB, initialize


@pytest.mark.modal
@pytest.mark.anyio
async def test_live_modal_create_health_reconnect_and_terminate(tmp_path) -> None:
    if os.getenv("GG_RUN_MODAL_TESTS") != "1":
        pytest.skip("set GG_RUN_MODAL_TESTS=1 to run the live Modal smoke")

    initialize(tmp_path / "runtime.db")
    ledger = TaskLedger(SQLiteDB(tmp_path / "runtime.db"))
    ledger.open()
    task, _ = ledger.submit(
        idempotency_key="modal-live-smoke",
        repository="owner/repo",
        prompt="live lifecycle smoke only",
        base_ref=None,
        retry_of=None,
    )
    provider = ModalProvider(
        app_name=os.getenv("GG_MODAL_APP_NAME", DEFAULT_MODAL_APP_NAME),
        image_name=os.getenv("GG_MODAL_IMAGE_NAME", DEFAULT_MODAL_IMAGE_NAME),
    )
    lifecycle = ModalSandboxLifecycle(
        ledger=ledger,
        provider=provider,
        deployment=os.getenv("GG_MODAL_DEPLOYMENT", DEFAULT_MODAL_DEPLOYMENT),
    )

    try:
        created = await lifecycle.create(task.id)
        assert created.state is SandboxProviderState.RUNNING

        connection = await lifecycle.connect(task.id)
        async with connection.http_client(timeout=20) as client:
            response = await client.get("/health")
        response.raise_for_status()
        assert response.json()["status"] == "ok"
        async with connection.http_client(timeout=20) as client:
            created_conversation = await client.post(
                "/api/conversations", json={"working_dir": "sqlite-smoke"}
            )
            created_conversation.raise_for_status()
            url = f"/api/conversations/{created_conversation.json()['id']}/events"
            for index in range(5):
                sent = await client.post(url, json={"content": f"SQLite smoke {index}"})
                sent.raise_for_status()
            full = (await client.get(url)).json()
            collected = []
            after = 0
            while True:
                page_response = await client.get(
                    url, params={"after": after, "limit": 2}
                )
                page_response.raise_for_status()
                page = page_response.json()
                if not page:
                    break
                assert len(page) <= 2 and page[0]["seq"] > after
                collected.extend(page)
                after = page[-1]["seq"]
            assert collected == full

        fresh_provider = ModalProvider(
            app_name=os.getenv("GG_MODAL_APP_NAME", DEFAULT_MODAL_APP_NAME),
            image_name=os.getenv("GG_MODAL_IMAGE_NAME", DEFAULT_MODAL_IMAGE_NAME),
        )
        fresh = ModalSandboxLifecycle(
            ledger=ledger,
            provider=fresh_provider,
            deployment=os.getenv("GG_MODAL_DEPLOYMENT", DEFAULT_MODAL_DEPLOYMENT),
        )
        reconnected = await fresh.reconnect(task.id)
        assert reconnected.provider_id == created.provider_id
        assert reconnected.state is SandboxProviderState.RUNNING

        stopped = await fresh.terminate(task.id)
        assert stopped.state is SandboxProviderState.STOPPED
        assert (await fresh.inspect(task.id)).state is SandboxProviderState.STOPPED
    finally:
        try:
            await lifecycle.terminate(task.id)
        except Exception:
            pass
        ledger.close()
