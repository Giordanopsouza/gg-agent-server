"""Host-side GitHub REST adapter for draft pull-request publication.

Credentials are supplied only as an Authorization header. Callers never see
the token in records, URLs, or exception text.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import quote

import httpx


GITHUB_API_VERSION = "2022-11-28"
GITHUB_ACCEPT = "application/vnd.github+json"


class GitHubError(RuntimeError):
    """A GitHub API call failed."""


class GitHubTimeoutError(GitHubError):
    """The GitHub API did not return a timely response."""


@dataclass(frozen=True)
class RemotePullRequest:
    """Credential-free view of one GitHub pull request."""

    number: int
    html_url: str
    draft: bool
    state: str
    author: str
    title: str
    body: str
    head_ref: str
    base_ref: str
    head_sha: str


class GitHubGateway(Protocol):
    async def get_authenticated_login(self) -> str: ...

    async def get_branch_sha(self, repository: str, branch: str) -> str | None: ...

    async def list_pull_requests(
        self,
        repository: str,
        *,
        head: str,
        base: str,
        state: str = "all",
    ) -> tuple[RemotePullRequest, ...]: ...

    async def create_draft_pull_request(
        self,
        repository: str,
        *,
        title: str,
        body: str,
        head: str,
        base: str,
    ) -> RemotePullRequest: ...


def _owner_repo(repository: str) -> tuple[str, str]:
    owner, separator, name = repository.partition("/")
    if not separator or not owner or not name or "/" in name:
        raise GitHubError(f"repository must be 'owner/name', got {repository!r}")
    return owner, name


def _redact(text: str, token: str) -> str:
    if not token:
        return text
    return text.replace(token, "[REDACTED]")


def _parse_pull(payload: dict[str, Any]) -> RemotePullRequest:
    user = payload.get("user") or {}
    head = payload.get("head") or {}
    base = payload.get("base") or {}
    return RemotePullRequest(
        number=int(payload["number"]),
        html_url=str(payload["html_url"]),
        draft=bool(payload.get("draft", False)),
        state=str(payload.get("state", "open")),
        author=str(user.get("login") or ""),
        title=str(payload.get("title") or ""),
        body=str(payload.get("body") or ""),
        head_ref=str(head.get("ref") or ""),
        base_ref=str(base.get("ref") or ""),
        head_sha=str(head.get("sha") or ""),
    )


class HttpGitHubGateway:
    """GitHub REST client that never logs or returns the bot token."""

    def __init__(
        self,
        token: str,
        *,
        api_url: str = "https://api.github.com",
        timeout_seconds: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not token or token != token.strip():
            raise GitHubError("GitHub token must be a non-empty secret")
        self._token = token
        self._api_url = api_url.rstrip("/")
        self._timeout = timeout_seconds
        self._client = client

    def __repr__(self) -> str:
        return f"HttpGitHubGateway(api_url={self._api_url!r})"

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": GITHUB_ACCEPT,
            "Authorization": f"Bearer {self._token}",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
        }

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        url = f"{self._api_url}{path}"
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            response = await client.request(
                method, url, headers=self._headers(), **kwargs
            )
        except httpx.TimeoutException as exc:
            raise GitHubTimeoutError(
                _redact(f"GitHub request timed out: {exc}", self._token)
            ) from exc
        except httpx.HTTPError as exc:
            raise GitHubError(
                _redact(f"GitHub request failed: {exc}", self._token)
            ) from exc
        finally:
            if owns_client:
                await client.aclose()
        return response

    def _raise_for_status(self, response: httpx.Response, *, action: str) -> None:
        if response.is_success:
            return
        detail = _redact(response.text, self._token)
        raise GitHubError(
            f"GitHub {action} failed with HTTP {response.status_code}: {detail}"
        )

    async def get_authenticated_login(self) -> str:
        response = await self._request("GET", "/user")
        self._raise_for_status(response, action="get authenticated user")
        payload = response.json()
        login = str(payload.get("login") or "")
        if not login:
            raise GitHubError("GitHub /user response did not include login")
        return login

    async def get_branch_sha(self, repository: str, branch: str) -> str | None:
        owner, name = _owner_repo(repository)
        encoded = quote(branch, safe="/")
        response = await self._request(
            "GET", f"/repos/{owner}/{name}/git/ref/heads/{encoded}"
        )
        if response.status_code == 404:
            return None
        self._raise_for_status(response, action="get branch ref")
        payload = response.json()
        sha = str((payload.get("object") or {}).get("sha") or "")
        return sha or None

    async def list_pull_requests(
        self,
        repository: str,
        *,
        head: str,
        base: str,
        state: str = "all",
    ) -> tuple[RemotePullRequest, ...]:
        owner, name = _owner_repo(repository)
        head_filter = head if ":" in head else f"{owner}:{head}"
        found: list[RemotePullRequest] = []
        page = 1
        while page <= 3:
            response = await self._request(
                "GET",
                f"/repos/{owner}/{name}/pulls",
                params={
                    "state": state,
                    "head": head_filter,
                    "base": base,
                    "per_page": 100,
                    "page": page,
                },
            )
            self._raise_for_status(response, action="list pull requests")
            payload = response.json()
            if not isinstance(payload, list) or not payload:
                break
            found.extend(_parse_pull(item) for item in payload)
            if len(payload) < 100:
                break
            page += 1
        return tuple(found)

    async def create_draft_pull_request(
        self,
        repository: str,
        *,
        title: str,
        body: str,
        head: str,
        base: str,
    ) -> RemotePullRequest:
        owner, name = _owner_repo(repository)
        response = await self._request(
            "POST",
            f"/repos/{owner}/{name}/pulls",
            json={
                "title": title,
                "body": body,
                "head": head,
                "base": base,
                "draft": True,
            },
        )
        self._raise_for_status(response, action="create draft pull request")
        return _parse_pull(response.json())


__all__ = [
    "GITHUB_ACCEPT",
    "GITHUB_API_VERSION",
    "GitHubError",
    "GitHubGateway",
    "GitHubTimeoutError",
    "HttpGitHubGateway",
    "RemotePullRequest",
]
