from __future__ import annotations

import json
from types import TracebackType
from urllib.parse import urlsplit, urlunsplit

import httpx
from websockets.sync.client import ClientConnection, connect

from gg.sdk.domain import ConversationRecord, ConversationStatus, Event
from gg.sdk.remote_workspace import RemoteWorkspace


class RemoteEventSubscription:
    """A blocking iterator over one conversation's WebSocket events."""

    def __init__(self, workspace: RemoteWorkspace, conversation_id: str) -> None:
        self._workspace = workspace
        self._conversation_id = conversation_id
        self._connection: ClientConnection | None = None

    def __enter__(self) -> RemoteEventSubscription:
        self._connection = connect(
            _websocket_url(self._workspace.host, self._conversation_id),
            open_timeout=self._workspace.timeout,
            close_timeout=5,
        )
        if self._workspace.api_key is not None:
            self._connection.send(
                json.dumps(
                    {
                        "type": "auth",
                        "session_api_key": self._workspace.api_key,
                    }
                )
            )
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def __iter__(self) -> RemoteEventSubscription:
        return self

    def __next__(self) -> Event:
        return self.receive()

    def receive(self, *, timeout: float | None = None) -> Event:
        """Wait for and validate the next event frame."""
        if self._connection is None:
            raise RuntimeError("subscription must be entered before receiving events")
        raw = self._connection.recv(timeout=timeout)
        if isinstance(raw, bytes):
            raw = raw.decode()
        return Event.model_validate_json(raw)


class RemoteConversation:
    """Synchronous HTTP proxy for a conversation owned by an agent server."""

    def __init__(
        self,
        *,
        workspace: RemoteWorkspace,
        conversation_id: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.workspace = workspace
        self._client = client or workspace.client

        payload: dict[str, str] = {"working_dir": workspace.working_dir}
        if conversation_id is not None:
            payload["id"] = conversation_id
        response = self._client.post(
            "/api/conversations",
            json=payload,
            headers=workspace.headers,
        )
        response.raise_for_status()
        self._record = ConversationRecord.model_validate(response.json())

    @property
    def id(self) -> str:
        return self._record.id

    @property
    def status(self) -> ConversationStatus:
        return self._record.status

    def send_message(self, text: str) -> Event:
        """Persist a message without implicitly running the agent."""
        response = self._client.post(
            f"/api/conversations/{self.id}/events",
            json={"content": text, "run": False},
            headers=self.workspace.headers,
        )
        response.raise_for_status()
        return Event.model_validate(response.json())

    def run(self) -> None:
        """Run the remote agent loop and wait for it to finish."""
        response = self._client.post(
            f"/api/conversations/{self.id}/run",
            headers=self.workspace.headers,
        )
        response.raise_for_status()
        self._record = ConversationRecord.model_validate(response.json())

    def list_events(self) -> list[Event]:
        """Fetch the persisted event history in sequence order."""
        response = self._client.get(
            f"/api/conversations/{self.id}/events",
            headers=self.workspace.headers,
        )
        response.raise_for_status()
        return [Event.model_validate(item) for item in response.json()]

    def subscribe(self) -> RemoteEventSubscription:
        """Return a context-managed blocking WebSocket event iterator."""
        return RemoteEventSubscription(self.workspace, self.id)


def _websocket_url(host: str, conversation_id: str) -> str:
    parsed = urlsplit(host)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    path = f"{parsed.path.rstrip('/')}/sockets/events/{conversation_id}"
    return urlunsplit((scheme, parsed.netloc, path, "", ""))
