"""SQLite credential isolation, durability and the actual dispatch boundary."""

import shutil

import httpx
import pytest
from cryptography.fernet import Fernet
from test_google_auth import callback, google_app as google_app, start
from test_model_credential_dispatch import FakeLedger, FakeProvider

from gg.runtime.checkpoints import CheckpointCoordinator
from gg.runtime.modal_sandbox import CredentialUnavailableError, ModalSandboxLifecycle
from gg.runtime.openrouter_vault import (
    OpenRouterKeyVerifier,
    SQLiteOpenRouterVault,
    openrouter_vault_router,
)
from gg.runtime.sqlite_db import SQLiteDB


@pytest.mark.anyio
async def test_versions_ciphertext_isolation_restore_and_dispatch(google_app, tmp_path):
    _, _, _, _, sessions, checkpoints = google_app
    a = (await sessions.user(await sessions.create("a", "a@example.com")))["id"]
    b = (await sessions.user(await sessions.create("b", "b@example.com")))["id"]
    key = Fernet.generate_key().decode()
    vault = SQLiteOpenRouterVault(sessions.db, key, checkpoints)
    secret_a, secret_b = "sk-or-personal-a-1234", "sk-or-personal-b-5678"
    assert vault.replace(a, secret_a)["version"] == 1
    assert vault.replace(a, secret_a)["version"] == 2
    assert vault.replace(b, secret_b)["version"] == 1
    assert vault.remove(a)["version"] == 3
    assert vault.remove(a)["version"] == 4
    assert vault.resolve(a) is None
    assert vault.replace(a, secret_a)["version"] == 5
    await vault.ensure_durable()
    with sessions.db.read() as connection:
        rows = connection.execute("SELECT * FROM openrouter_credentials").fetchall()
        assert secret_a not in str(rows) and secret_b not in str(rows)
        assert key not in str(rows)
    snapshot = tmp_path / "restored"
    shutil.copyfile(checkpoints.snapshot, snapshot)

    async def commit():
        pass

    with SQLiteDB(snapshot) as db:
        restored = SQLiteOpenRouterVault(
            db, key, CheckpointCoordinator(db, tmp_path / "snapshot2", commit)
        )
        assert restored.resolve(a) == (secret_a, 5)
        assert restored.resolve(b) == (secret_b, 1)
        ledger, provider = FakeLedger(), FakeProvider()
        from uuid import UUID

        ledger.tasks["a"] = ledger.tasks["a"].model_copy(update={"owner_id": UUID(a)})
        ledger.tasks["b"] = ledger.tasks["b"].model_copy(update={"owner_id": UUID(b)})
        lifecycle = ModalSandboxLifecycle(
            ledger=ledger,
            provider=provider,
            deployment="test",
            credential_vault=restored,
        )
        await lifecycle.create("a")
        await lifecycle.create("b")
        assert [
            call["sandbox_env"]["OPENROUTER_API_KEY"] for call in provider.calls
        ] == [secret_a, secret_b]
        assert [ledger.creations[task].credential_version for task in ("a", "b")] == [
            5,
            1,
        ]
        assert secret_a not in str(ledger.creations)
        assert secret_b not in str(ledger.creations)
        restored.remove(a)
        ledger.creations.pop("a")
        with pytest.raises(CredentialUnavailableError):
            await lifecycle.create("a")
        assert len(provider.calls) == 2


def test_http_ownership_redaction_and_checkpoint_failure(google_app):
    client, settings, state, auth, sessions, checkpoints = google_app
    key = Fernet.generate_key().decode()
    vault = SQLiteOpenRouterVault(sessions.db, key, checkpoints)
    verifier = OpenRouterKeyVerifier(
        httpx.MockTransport(lambda request: httpx.Response(200))
    )
    client.app.include_router(
        openrouter_vault_router(settings, sessions, vault, verifier)
    )
    path, origin = "/auth/openrouter-credential", {"Origin": settings.web_origin}
    assert client.get(path).status_code == 401
    callback(client, start(client, state)[0])
    token_a = client.cookies.get("gg_session")
    secret_a, secret_b = "sk-or-personal-a-1234", "sk-or-personal-b-5678"
    assert client.put(path, json={"api_key": secret_a}).status_code == 403
    saved = client.put(path, json={"api_key": secret_a}, headers=origin)
    assert saved.json() == {"configured": True, "mask": "••••1234", "version": 1}
    assert checkpoints.confirmed_revision == sessions.db.revision
    state["claims"] = {"sub": "google-b", "email": "b@example.com"}
    callback(client, start(client, state)[0])
    assert client.get(path).json()["configured"] is False
    assert (
        client.put(path, json={"api_key": secret_b}, headers=origin).json()["version"]
        == 1
    )
    client.cookies.set("gg_session", token_a, domain="app.example", path="/")
    assert client.get(path).json()["mask"] == "••••1234"
    # Save commits locally, but the route cannot acknowledge before checkpoint.
    state["fail"] = True
    response = client.put(path, json={"api_key": secret_a}, headers=origin)
    assert response.status_code == 503
    assert secret_a not in response.text and "private" not in response.text
    state["fail"] = False
    assert (
        client.put(path, json={"api_key": secret_a}, headers=origin).json()["version"]
        == 3
    )
    state["fail"] = True
    response = client.delete(path, headers=origin)
    assert response.status_code == 503
    state["fail"] = False
    response = client.delete(path, headers=origin)
    assert response.json() == {"configured": False, "mask": None, "version": 5}
    assert client.get(path).json()["configured"] is False
    assert secret_a not in response.text and key not in response.text
