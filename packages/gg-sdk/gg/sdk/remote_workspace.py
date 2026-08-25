from __future__ import annotations

from pathlib import Path

import httpx


SESSION_API_KEY_HEADER = "X-Session-API-Key"


class RemoteWorkspace:
    """Connection details for a workspace hosted by an agent server."""

    def __init__(
        self,
        *,
        host: str,
        working_dir: str | Path = "/workspace/project",
        api_key: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        if not host.strip():
            raise ValueError("host must not be empty")
        self.host = host.rstrip("/")
        self.working_dir = str(working_dir)
        self.api_key = api_key
        self.timeout = timeout
        self._client: httpx.Client | None = None

    @property
    def headers(self) -> dict[str, str]:
        """Headers required by the remote agent server."""
        if self.api_key is None:
            return {}
        return {SESSION_API_KEY_HEADER: self.api_key}

    @property
    def client(self) -> httpx.Client:
        """Create the shared HTTP client lazily."""
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.host,
                headers=self.headers,
                timeout=self.timeout,
            )
        return self._client

    def close(self) -> None:
        """Close the lazily-created HTTP client, if one exists."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> RemoteWorkspace:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
