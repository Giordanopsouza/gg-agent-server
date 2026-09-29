"""The provider boundary receives only the matching owner's current key."""

from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest

from gg.runtime.ledger import SandboxCreationRecord, SandboxProviderState
from gg.runtime.modal_sandbox import CredentialUnavailableError, ModalSandboxLifecycle
from gg.runtime.openrouter_vault import OpenRouterKeyVerifier
from gg.sdk.tasks import TaskRecord


class FakeLedger:
    def __init__(self) -> None:
        self.tasks = {
            "a": TaskRecord(
                id="a",
                seq=1,
                idempotency_key="a",
                prompt="a",
                owner_id=UUID("00000000-0000-0000-0000-000000000001"),
                model="z-ai/glm-5.3-flashx",
            ),
            "b": TaskRecord(
                id="b",
                seq=2,
                idempotency_key="b",
                prompt="b",
                owner_id=UUID("00000000-0000-0000-0000-000000000002"),
                model="anthropic/claude-sonnet-4.5",
            ),
        }
        self.creations: dict[str, SandboxCreationRecord] = {}

    def get(self, task_id: str) -> TaskRecord:
        return self.tasks[task_id]

    def get_sandbox_creation(self, task_id: str):
        return self.creations.get(task_id)

    def begin_sandbox_creation(self, **kwargs: object):
        task_id = str(kwargs["task_id"])
        now = datetime.now(UTC)
        record = SandboxCreationRecord(
            **kwargs,
            provider_id=None,
            provider_state=SandboxProviderState.CREATING,
            detail=None,
            created_at=now,
            updated_at=now,
        )
        self.creations[task_id] = record
        return record, True

    def update_sandbox_creation(self, task_id: str, **changes: object):
        record = replace(self.creations[task_id], **changes)
        self.creations[task_id] = record
        return record

    def record_base_sha(self, task_id: str, base_sha: str) -> None:
        self.tasks[task_id] = self.tasks[task_id].model_copy(
            update={"base_sha": base_sha}
        )


class FakeVault:
    def __init__(self) -> None:
        self.keys = {
            "00000000-0000-0000-0000-000000000001": ("key-a", 3),
            "00000000-0000-0000-0000-000000000002": ("key-b", 7),
        }

    def resolve(self, owner_id: str):
        return self.keys.get(owner_id)


class FakeProvider:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.handles: dict[str, object] = {}

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        handle = type("Handle", (), {"object_id": f"sandbox-{len(self.calls)}"})()
        self.handles[handle.object_id] = handle
        return handle

    async def from_id(self, provider_id: str):
        return self.handles[provider_id]

    async def poll(self, handle):
        return None

    async def wait_until_ready(self, handle, *, timeout):
        pass


@pytest.mark.anyio
async def test_two_users_receive_only_their_own_current_key() -> None:
    ledger = FakeLedger()
    vault = FakeVault()
    provider = FakeProvider()
    lifecycle = ModalSandboxLifecycle(
        ledger=ledger,
        provider=provider,
        deployment="test",
        credential_vault=vault,
        sandbox_env={"OPENROUTER_API_KEY": "global-key"},
    )

    await lifecycle.create("a")
    await lifecycle.create("b")

    assert [call["sandbox_env"]["OPENROUTER_API_KEY"] for call in provider.calls] == [
        "key-a",
        "key-b",
    ]
    assert ledger.creations["a"].credential_version == 3
    assert ledger.creations["b"].credential_version == 7
    assert "key-a" not in str(ledger.creations)
    assert "key-b" not in str(ledger.creations)

    vault.keys.pop("00000000-0000-0000-0000-000000000001")
    await lifecycle.create("a")
    assert len(provider.calls) == 2


@pytest.mark.anyio
async def test_removed_key_blocks_web_sandbox_creation() -> None:
    ledger = FakeLedger()
    vault = FakeVault()
    vault.keys.pop("00000000-0000-0000-0000-000000000001")
    provider = FakeProvider()
    lifecycle = ModalSandboxLifecycle(
        ledger=ledger,
        provider=provider,
        deployment="test",
        credential_vault=vault,
    )
    with pytest.raises(CredentialUnavailableError, match="personal OpenRouter key"):
        await lifecycle.create("a")
    assert provider.calls == []
    assert ledger.creations == {}


@pytest.mark.anyio
async def test_revoked_key_blocks_before_provider_creation() -> None:
    ledger = FakeLedger()
    provider = FakeProvider()
    seen: list[str | None] = []

    def response(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("Authorization"))
        return httpx.Response(401)

    lifecycle = ModalSandboxLifecycle(
        ledger=ledger,
        provider=provider,
        deployment="test",
        credential_vault=FakeVault(),
        credential_verifier=OpenRouterKeyVerifier(httpx.MockTransport(response)),
    )
    with pytest.raises(CredentialUnavailableError, match="key invalid"):
        await lifecycle.create("a")
    assert seen == ["Bearer key-a"]
    assert provider.calls == []
    assert ledger.creations == {}


@pytest.mark.anyio
async def test_owner_repository_sandbox_gets_the_task_credential_only() -> None:
    ledger = FakeLedger()
    ledger.tasks["repo"] = ledger.tasks["a"].model_copy(
        update={
            "id": "repo",
            "idempotency_key": "repo",
            "repository": "alice/private",
            "base_ref": "main",
        }
    )
    provider = FakeProvider()

    class Authorization:
        def credential(self, owner_id, repository, base_ref):
            assert repository == "alice/private"
            assert base_ref == "main"
            return SimpleNamespace(token="installation-token", base_sha="abc123")

    lifecycle = ModalSandboxLifecycle(
        ledger=ledger,
        provider=provider,
        deployment="test",
        credential_vault=FakeVault(),
        repository_authorization=Authorization(),
        sandbox_env={
            "OPENROUTER_API_KEY": "global-key",
            "GG_GITHUB_CLONE_TOKEN": "global-clone-token",
            "GH_TOKEN": "global-gh-token",
            "GITHUB_TOKEN": "global-github-token",
        },
    )
    await lifecycle.create("repo")
    env = provider.calls[0]["sandbox_env"]
    assert env["OPENROUTER_API_KEY"] == "key-a"
    assert env["GG_GITHUB_CLONE_TOKEN"] == "installation-token"
    assert env["GG_PI_OWNS_PUBLICATION"] == "1"
    assert "GH_TOKEN" not in env
    assert "GITHUB_TOKEN" not in env
    assert "global-clone-token" not in env.values()
    assert "global-gh-token" not in env.values()
