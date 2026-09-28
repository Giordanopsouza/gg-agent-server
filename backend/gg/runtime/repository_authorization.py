"""Live user/installation intersection and short-lived repository credentials."""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from gg.runtime.github_connection import PostgresGitHubConnections


class RepositoryAccessError(ValueError):
    """The account, installation, repository, or branch is unavailable."""


@dataclass(frozen=True)
class AuthorizedRepository:
    id: int
    full_name: str
    private: bool
    default_branch: str
    installation_id: int


@dataclass(frozen=True)
class InstallationCredential:
    token: str
    expires_at: datetime
    repository: AuthorizedRepository
    base_sha: str


class RepositoryAuthorization:
    """Never trusts a browser installation ID or a previously stored snapshot."""

    def __init__(
        self,
        connections: PostgresGitHubConnections,
        *,
        client_id: str,
        private_key: str | None,
        client: httpx.Client | None = None,
    ) -> None:
        self.connections = connections
        self.client_id = client_id
        self.private_key = private_key
        self.client = client

    def _request(self, method: str, path: str, token: str, **kwargs: Any) -> Any:
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        try:
            if self.client is None:
                with httpx.Client(
                    base_url="https://api.github.com", timeout=10
                ) as client:
                    response = client.request(method, path, headers=headers, **kwargs)
            else:
                response = self.client.request(method, path, headers=headers, **kwargs)
            if not response.is_success:
                raise RepositoryAccessError("GitHub access unavailable")
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise RepositoryAccessError("GitHub access unavailable") from exc

    def _user_token(self, owner_id: UUID) -> str:
        current = self.connections.current(str(owner_id))
        if current is None or current[2] is None or current[3] == "revoked":
            raise RepositoryAccessError("GitHub account must be connected")
        token = current[2]
        identity = self._request("GET", "/user", token)
        if identity.get("id") != current[0]:
            raise RepositoryAccessError("GitHub account changed; reconnect")
        return token

    def list_repositories(self, owner_id: UUID) -> list[AuthorizedRepository]:
        token = self._user_token(owner_id)
        result: dict[int, AuthorizedRepository] = {}
        for page in range(1, 11):
            installations = self._request(
                "GET",
                "/user/installations",
                token,
                params={"per_page": 100, "page": page},
            ).get("installations")
            if not isinstance(installations, list):
                raise RepositoryAccessError("invalid GitHub installation response")
            for installation in installations:
                if installation.get("suspended_at") is not None:
                    continue
                installation_id = installation.get("id")
                permissions = installation.get("permissions") or {}
                if type(installation_id) is not int or not (
                    permissions.get("contents") == "write"
                    and permissions.get("pull_requests") == "write"
                ):
                    continue
                for repo_page in range(1, 11):
                    repos = self._request(
                        "GET",
                        f"/user/installations/{installation_id}/repositories",
                        token,
                        params={"per_page": 100, "page": repo_page},
                    ).get("repositories")
                    if not isinstance(repos, list):
                        raise RepositoryAccessError(
                            "invalid GitHub repository response"
                        )
                    for repo in repos:
                        access = repo.get("permissions") or {}
                        repo_id, name = repo.get("id"), repo.get("full_name")
                        if not (access.get("push") or access.get("admin")):
                            continue
                        if type(repo_id) is not int or not isinstance(name, str):
                            raise RepositoryAccessError(
                                "invalid GitHub repository response"
                            )
                        result[repo_id] = AuthorizedRepository(
                            id=repo_id,
                            full_name=name,
                            private=bool(repo.get("private")),
                            default_branch=str(repo.get("default_branch") or ""),
                            installation_id=installation_id,
                        )
                    if len(repos) < 100:
                        break
                else:
                    raise RepositoryAccessError("GitHub repository list exceeds limit")
            if len(installations) < 100:
                return sorted(result.values(), key=lambda repo: repo.full_name.lower())
        raise RepositoryAccessError("GitHub installation list exceeds limit")

    def branches(self, owner_id: UUID, repository: str) -> list[dict[str, str]]:
        authorized = self._find(owner_id, repository)
        token = self._user_token(owner_id)
        branches: list[dict[str, str]] = []
        path = quote(authorized.full_name, safe="/")
        for page in range(1, 11):
            items = self._request(
                "GET",
                f"/repos/{path}/branches",
                token,
                params={"per_page": 100, "page": page},
            )
            if not isinstance(items, list):
                raise RepositoryAccessError("invalid GitHub branch response")
            for item in items:
                name = item.get("name")
                sha = (item.get("commit") or {}).get("sha")
                if not isinstance(name, str) or not isinstance(sha, str):
                    raise RepositoryAccessError("invalid GitHub branch response")
                branches.append({"name": name, "sha": sha})
            if len(items) < 100:
                return branches
        raise RepositoryAccessError("GitHub branch list exceeds limit")

    def _find(self, owner_id: UUID, repository: str) -> AuthorizedRepository:
        for item in self.list_repositories(owner_id):
            if item.full_name.lower() == repository.lower():
                return item
        raise RepositoryAccessError("repository is not authorized")

    def resolve(
        self, owner_id: UUID, repository: str, base_ref: str
    ) -> tuple[AuthorizedRepository, str]:
        item = self._find(owner_id, repository)
        token = self._user_token(owner_id)
        path = quote(item.full_name, safe="/")
        branch = quote(base_ref, safe="")
        try:
            payload = self._request("GET", f"/repos/{path}/branches/{branch}", token)
        except RepositoryAccessError as exc:
            raise RepositoryAccessError("branch is not available") from exc
        sha = (payload.get("commit") or {}).get("sha")
        if (
            not isinstance(sha, str)
            or len(sha) != 40
            or any(c not in "0123456789abcdef" for c in sha)
        ):
            raise RepositoryAccessError("invalid GitHub branch SHA")
        return item, sha

    def _app_jwt(self) -> str:
        if not self.private_key:
            raise RepositoryAccessError("GitHub App private key is not configured")

        def encode(value: dict[str, Any]) -> str:
            return (
                base64.urlsafe_b64encode(
                    json.dumps(value, separators=(",", ":")).encode()
                )
                .rstrip(b"=")
                .decode()
            )

        now = int(time.time())
        header = encode({"alg": "RS256", "typ": "JWT"})
        claims = encode({"iat": now - 60, "exp": now + 540, "iss": self.client_id})
        message = f"{header}.{claims}"
        try:
            key = serialization.load_pem_private_key(
                self.private_key.encode(), password=None
            )
            signature = key.sign(message.encode(), padding.PKCS1v15(), hashes.SHA256())
        except (ValueError, TypeError, AttributeError) as exc:
            raise RepositoryAccessError("invalid GitHub App private key") from exc
        return f"{message}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}"

    def credential(
        self, owner_id: UUID, repository: str, base_ref: str
    ) -> InstallationCredential:
        item, sha = self.resolve(owner_id, repository, base_ref)
        payload = self._request(
            "POST",
            f"/app/installations/{item.installation_id}/access_tokens",
            self._app_jwt(),
            json={
                "repository_ids": [item.id],
                "permissions": {"contents": "write", "pull_requests": "write"},
            },
        )
        token = payload.get("token")
        try:
            expires_at = datetime.fromisoformat(
                payload["expires_at"].replace("Z", "+00:00")
            ).astimezone(UTC)
        except (KeyError, ValueError, AttributeError) as exc:
            raise RepositoryAccessError("invalid installation token response") from exc
        repos = payload.get("repositories") or []
        if (
            not isinstance(token, str)
            or not token
            or len(repos) != 1
            or repos[0].get("id") != item.id
        ):
            raise RepositoryAccessError(
                "installation token was not restricted to repository"
            )
        # Dispatch permits a 45-minute run from reservation plus five minutes
        # of margin. GitHub normally issues a token valid for one hour.
        if (expires_at - datetime.now(UTC)).total_seconds() < 50 * 60:
            raise RepositoryAccessError("installation token expires too soon")
        return InstallationCredential(token, expires_at, item, sha)
