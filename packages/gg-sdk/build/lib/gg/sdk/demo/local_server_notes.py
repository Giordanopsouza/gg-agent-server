"""Local-server demo: dummy agent writes NOTES.md over HTTP and WebSocket.

The server must already be running. This module talks to it as a client. It
does not import LocalConversation.

Start the server, then run this::

    uv run python -m gg.server --host 127.0.0.1 --port 8000
    uv run python -m gg.sdk.demo.local_server_notes
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse, urlunparse

import httpx
from websockets.sync.client import connect

from gg.sdk.domain import ConversationRecord, Event


DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_MESSAGE = "hello from the local-server demo"
DEFAULT_WORKING_DIR = "work"
# message + running + write action + observation + finished
EVENTS_AFTER_RUN = 5


class JsonSocket(Protocol):
    def receive_json(self) -> dict[str, Any]: ...


WsConnect = Callable[[str], AbstractContextManager[JsonSocket]]


@dataclass(frozen=True)
class DemoResult:
    conversation_id: str
    working_dir: Path
    notes_path: Path
    events: list[Event]
    live_events: list[Event]
    reconnect_events: list[Event]


class _LiveJsonSocket:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def receive_json(self) -> dict[str, Any]:
        raw = self._connection.recv(timeout=10)
        if isinstance(raw, bytes):
            raw = raw.decode()
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise TypeError(f"expected a JSON object, got {type(payload).__name__}")
        return payload


@contextmanager
def live_websocket(base_url: str, conversation_id: str) -> Iterator[JsonSocket]:
    """Open a JSON WebSocket against a running server."""
    url = _websocket_url(base_url, conversation_id)
    with connect(url, open_timeout=10, close_timeout=5) as connection:
        yield _LiveJsonSocket(connection)


def run_demo(
    client: httpx.Client,
    *,
    websocket_connect: WsConnect,
    message: str = DEFAULT_MESSAGE,
    working_dir: str = DEFAULT_WORKING_DIR,
) -> DemoResult:
    """Create, send, run, drop the socket, reconnect, and check NOTES.md."""
    health = client.get("/health")
    health.raise_for_status()

    created = client.post("/api/conversations", json={"working_dir": working_dir})
    created.raise_for_status()
    record = ConversationRecord.model_validate(created.json())
    conversation_id = record.id
    workspace = Path(record.working_dir)

    with websocket_connect(conversation_id) as socket:
        sent = client.post(
            f"/api/conversations/{conversation_id}/events",
            json={"content": message},
        )
        sent.raise_for_status()
        ran = client.post(f"/api/conversations/{conversation_id}/run")
        ran.raise_for_status()
        live_events = _collect_events(socket, EVENTS_AFTER_RUN)

    with websocket_connect(conversation_id) as socket:
        reconnect_events = _collect_events(socket, EVENTS_AFTER_RUN)

    listed = client.get(f"/api/conversations/{conversation_id}/events")
    listed.raise_for_status()
    events = [Event.model_validate(item) for item in listed.json()]

    notes_path = workspace / "NOTES.md"
    if not notes_path.is_file():
        raise FileNotFoundError(f"NOTES.md missing at {notes_path}")
    if not events:
        raise RuntimeError("GET /events returned no history after reconnect")

    return DemoResult(
        conversation_id=conversation_id,
        working_dir=workspace,
        notes_path=notes_path,
        events=events,
        live_events=live_events,
        reconnect_events=reconnect_events,
    )


def _collect_events(socket: JsonSocket, count: int) -> list[Event]:
    return [Event.model_validate(socket.receive_json()) for _ in range(count)]


def _websocket_url(base_url: str, conversation_id: str) -> str:
    parsed = urlparse(base_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return urlunparse(
        (scheme, parsed.netloc, f"/sockets/events/{conversation_id}", "", "", "")
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the dummy agent against a local gg-agent-server."
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"Server origin (default: {DEFAULT_BASE_URL})",
    )
    args = parser.parse_args()

    def websocket_connect(conversation_id: str) -> AbstractContextManager[JsonSocket]:
        return live_websocket(args.base_url, conversation_id)

    try:
        with httpx.Client(base_url=args.base_url, timeout=10.0) as client:
            result = run_demo(client, websocket_connect=websocket_connect)
    except httpx.ConnectError:
        print(
            f"No server at {args.base_url}. Start one with:\n"
            "  uv run python -m gg.server --host 127.0.0.1 --port 8000",
            file=sys.stderr,
        )
        raise SystemExit(1) from None

    print(result.notes_path)
    print(f"{len(result.events)} events after reconnect")


if __name__ == "__main__":
    main()
