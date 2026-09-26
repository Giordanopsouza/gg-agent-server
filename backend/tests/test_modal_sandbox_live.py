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


@pytest.mark.modal
@pytest.mark.anyio
async def test_live_modal_create_health_reconnect_and_terminate(tmp_path) -> None:
    if os.getenv("GG_RUN_MODAL_TESTS") != "1":
        pytest.skip("set GG_RUN_MODAL_TESTS=1 to run the live Modal smoke")

    ledger = TaskLedger(db_path=str(tmp_path / "modal-live.sqlite"))
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
