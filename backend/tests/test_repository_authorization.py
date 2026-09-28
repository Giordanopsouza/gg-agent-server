"""Authorization is a live intersection, including at token issuance."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient

from gg.runtime.config import RuntimeSettings
from gg.runtime.modal_sandbox import CredentialUnavailableError, ModalSandboxLifecycle
from gg.runtime.repository_authorization import (
    RepositoryAccessError,
    RepositoryAuthorization,
)
from gg.runtime.task_routes import router as task_router
from gg.runtime.task_service import TaskService, TaskValidationError
from gg.sdk.tasks import CreateTaskRequest, TaskRecord


OWNER = UUID("11111111-1111-4111-8111-111111111111")
OTHER = UUID("22222222-2222-4222-8222-222222222222")
SHA = "a" * 40


class Connections:
    def current(self, owner_id: str) -> tuple[int, str, str, str] | None:
        if owner_id == str(OWNER):
            return (10, "alice", "user-alice", "connected")
        return (20, "bob", "user-bob", "connected")


def test_live_repository_intersection_and_scoped_token() -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    state = {
        "repo_present": True,
        "user_write": True,
        "app_write": True,
        "expires_in": 3600,
        "token_requests": 0,
    }

    def github(request: httpx.Request) -> httpx.Response:
        token = request.headers["authorization"].removeprefix("Bearer ")
        path = request.url.path
        if path == "/user":
            return httpx.Response(200, json={"id": 10 if token == "user-alice" else 20})
        if path == "/user/installations":
            return httpx.Response(
                200,
                json={
                    "installations": [
                        {
                            "id": 55,
                            "permissions": {
                                "contents": "write" if state["app_write"] else "read",
                                "pull_requests": "write",
                            },
                        }
                    ]
                    if token == "user-alice"
                    else []
                },
            )
        if path == "/user/installations/55/repositories":
            return httpx.Response(
                200,
                json={
                    "repositories": [
                        {
                            "id": 100,
                            "full_name": "alice/private",
                            "private": True,
                            "default_branch": "main",
                            "permissions": {"push": state["user_write"]},
                        }
                    ]
                    if state["repo_present"]
                    else []
                },
            )
        if path == "/repos/alice/private/branches":
            return httpx.Response(200, json=[{"name": "main", "commit": {"sha": SHA}}])
        if path == "/repos/alice/private/branches/main":
            return httpx.Response(200, json={"commit": {"sha": SHA}})
        if path == "/app/installations/55/access_tokens":
            assert token.count(".") == 2  # JWT, never the user token.
            assert json.loads(request.read()) == {
                "repository_ids": [100],
                "permissions": {"contents": "write", "pull_requests": "write"},
            }
            state["token_requests"] += 1
            expires = datetime.now(UTC) + timedelta(seconds=state["expires_in"])
            return httpx.Response(
                201,
                json={
                    "token": "installation-repo-100",
                    "expires_at": expires.isoformat(),
                    "repositories": [{"id": 100}],
                },
            )
        return httpx.Response(404)

    with httpx.Client(
        base_url="https://api.github.com", transport=httpx.MockTransport(github)
    ) as client:
        authorization = RepositoryAuthorization(
            Connections(), client_id="Iv1.test", private_key=pem, client=client
        )
        repos = authorization.list_repositories(OWNER)
        assert [(repo.full_name, repo.private) for repo in repos] == [
            ("alice/private", True)
        ]
        assert authorization.branches(OWNER, "alice/private") == [
            {"name": "main", "sha": SHA}
        ]
        with pytest.raises(RepositoryAccessError):
            authorization.resolve(OTHER, "alice/private", "main")
        with pytest.raises(RepositoryAccessError):
            authorization.resolve(OWNER, "alice/forged", "main")
        credential = authorization.credential(OWNER, "alice/private", "main")
        assert credential.token == "installation-repo-100"
        assert credential.base_sha == SHA
        state["expires_in"] = 40 * 60
        with pytest.raises(RepositoryAccessError, match="expires too soon"):
            authorization.credential(OWNER, "alice/private", "main")
        state["expires_in"] = 3600
        state["repo_present"] = False
        with pytest.raises(RepositoryAccessError, match="not authorized"):
            authorization.credential(OWNER, "alice/private", "main")
        state["repo_present"] = True
        state["user_write"] = False
        with pytest.raises(RepositoryAccessError, match="not authorized"):
            authorization.credential(OWNER, "alice/private", "main")
        state["user_write"] = True
        state["app_write"] = False
        with pytest.raises(RepositoryAccessError, match="not authorized"):
            authorization.credential(OWNER, "alice/private", "main")
        assert state["token_requests"] == 2


def test_repository_routes_require_owner_and_use_live_authorization() -> None:
    class Authorization:
        def list_repositories(self, owner_id: UUID):
            assert owner_id == OWNER
            return [
                type(
                    "Repository",
                    (),
                    {
                        "__dict__": {
                            "id": 100,
                            "full_name": "alice/private",
                            "private": True,
                            "default_branch": "main",
                            "installation_id": 55,
                        }
                    },
                )()
            ]

        def branches(self, owner_id: UUID, repository: str):
            assert owner_id == OWNER
            if repository != "alice/private":
                raise RepositoryAccessError("repository is not authorized")
            return [{"name": "main", "sha": SHA}]

    def owner(request: Request) -> None:
        request.state.owner_id = OWNER if request.headers.get("x-owner") else None

    app = FastAPI()
    app.state.repository_authorization = Authorization()
    app.include_router(task_router, dependencies=[Depends(owner)])
    with TestClient(app) as client:
        assert client.get("/tasks/repositories").status_code == 403
        listing = client.get("/tasks/repositories", headers={"x-owner": "yes"})
        assert listing.status_code == 200
        assert listing.headers["cache-control"] == "no-store"
        assert listing.json()[0]["full_name"] == "alice/private"
        branches = client.get(
            "/tasks/repositories/alice/private/branches", headers={"x-owner": "yes"}
        )
        assert branches.json() == [{"name": "main", "sha": SHA}]
        forged = client.get(
            "/tasks/repositories/alice/other/branches", headers={"x-owner": "yes"}
        )
        assert forged.status_code == 403


@pytest.mark.anyio
async def test_dispatch_denies_removed_repository_before_provider_create() -> None:
    class Ledger:
        def get(self, task_id: str) -> TaskRecord:
            return TaskRecord(
                id=task_id,
                seq=1,
                owner_id=OWNER,
                idempotency_key="one",
                repository="alice/private",
                base_ref="main",
                prompt="edit",
            )

        def get_sandbox_creation(self, task_id: str):
            return None

        def begin_sandbox_creation(self, **kwargs):
            raise AssertionError("creation intent must not be written")

    class Vault:
        def resolve(self, owner_id: str):
            return "personal-key", 1

    class Authorization:
        def credential(self, owner_id: UUID, repository: str, base_ref: str):
            assert (owner_id, repository, base_ref) == (OWNER, "alice/private", "main")
            raise RepositoryAccessError("repository is not authorized")

    class Provider:
        async def create(self, **kwargs):
            raise AssertionError("sandbox must not be created")

    lifecycle = ModalSandboxLifecycle(
        ledger=Ledger(),
        provider=Provider(),
        deployment="test",
        credential_vault=Vault(),
        repository_authorization=Authorization(),
    )
    with pytest.raises(CredentialUnavailableError, match="not authorized"):
        await lifecycle.create("task-1")


def test_admission_denies_forged_repository_before_ledger_submit() -> None:
    class Ledger:
        def submit(self, **kwargs):
            raise AssertionError("unauthorized task must not enter the ledger")

    class Authorization:
        private_key = "configured"

        def resolve(self, owner_id: UUID, repository: str, base_ref: str):
            assert (owner_id, repository, base_ref) == (OWNER, "alice/forged", "main")
            raise RepositoryAccessError("repository is not authorized")

    service = TaskService(
        ledger=Ledger(),
        settings=RuntimeSettings(api_key="operator-secret"),
        repository_authorization=Authorization(),
    )
    with pytest.raises(TaskValidationError, match="not authorized"):
        service.submit(
            CreateTaskRequest(
                repository="alice/forged",
                base_ref="main",
                prompt="edit",
                idempotency_key="forged",
            ),
            owner_id=OWNER,
        )
