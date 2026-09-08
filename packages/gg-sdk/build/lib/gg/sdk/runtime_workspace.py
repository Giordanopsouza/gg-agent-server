from __future__ import annotations

from pathlib import Path

import httpx
from pydantic import BaseModel

from gg.sdk.remote_workspace import RemoteWorkspace


RUNTIME_API_KEY_HEADER = "X-API-Key"


class _StartSessionResponse(BaseModel):
    id: str
    url: str
    session_api_key: str


class RuntimeWorkspace(RemoteWorkspace):
    """A remote workspace provisioned through the runtime control API."""

    def __init__(
        self,
        *,
        runtime_api_url: str,
        runtime_api_key: str,
        working_dir: str | Path = "/workspace/project",
        timeout: float = 30.0,
        keep_alive: bool = False,
    ) -> None:
        if not runtime_api_url or runtime_api_url != runtime_api_url.strip():
            raise ValueError(
                "runtime_api_url must be non-empty and cannot contain "
                "surrounding whitespace"
            )
        if not runtime_api_key or runtime_api_key != runtime_api_key.strip():
            raise ValueError(
                "runtime_api_key must be non-empty and cannot contain "
                "surrounding whitespace"
            )

        # The real sandbox host and API key arrive from POST /start on entry.
        super().__init__(
            host="http://127.0.0.1:0",
            working_dir=working_dir,
            timeout=timeout,
        )
        self.runtime_api_url = runtime_api_url.rstrip("/")
        self.runtime_api_key = runtime_api_key
        self.keep_alive = keep_alive
        self.session_id: str | None = None
        self._runtime_client: httpx.Client | None = None

    @property
    def runtime_headers(self) -> dict[str, str]:
        """Headers required by the runtime control plane."""
        return {RUNTIME_API_KEY_HEADER: self.runtime_api_key}

    @property
    def runtime_client(self) -> httpx.Client:
        """Create the runtime control-plane client lazily."""
        if self._runtime_client is None:
            self._runtime_client = httpx.Client(
                base_url=self.runtime_api_url,
                headers=self.runtime_headers,
                timeout=self.timeout,
            )
        return self._runtime_client

    def __enter__(self) -> RuntimeWorkspace:
        if self.session_id is not None:
            raise RuntimeError("RuntimeWorkspace already owns a session")

        response = self.runtime_client.post("/start", headers=self.runtime_headers)
        response.raise_for_status()
        session = _StartSessionResponse.model_validate(response.json())

        self.session_id = session.id
        self.host = session.url.rstrip("/")
        self.api_key = session.session_api_key
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the sandbox client and stop the provisioned runtime session."""
        super().close()
        try:
            if self.session_id is not None and not self.keep_alive:
                response = self.runtime_client.post(
                    "/stop",
                    json={"id": self.session_id},
                    headers=self.runtime_headers,
                )
                response.raise_for_status()
                self.session_id = None
        finally:
            if self._runtime_client is not None:
                self._runtime_client.close()
                self._runtime_client = None
