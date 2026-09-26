from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport
from starlette.testclient import TestClient

from gg.sdk import ConversationStatus, MessageDeliveryStatus
from gg.server import Settings, create_app


_FAKE_ACTIVE_PI = r"""#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path


record_path = Path(os.environ["FAKE_PI_RECORD"])
prompt = json.loads(sys.stdin.buffer.readline())
state = {"prompt": prompt, "steers": []}


def send(message):
    sys.stdout.buffer.write(json.dumps(message).encode() + b"\n")
    sys.stdout.buffer.flush()


send({
    "id": prompt["id"],
    "type": "response",
    "command": "prompt",
    "success": True,
})
record_path.with_suffix(".ready").write_text("ready", encoding="utf-8")

for raw in sys.stdin.buffer:
    command = json.loads(raw)
    if command["type"] == "steer":
        state["steers"].append(command)
        send({
            "id": command["id"],
            "type": "response",
            "command": "steer",
            "success": True,
        })
    elif command["type"] == "abort":
        state["abort"] = command
        send({
            "id": command["id"],
            "type": "response",
            "command": "abort",
            "success": True,
        })
        record_path.write_text(json.dumps(state), encoding="utf-8")
"""


@pytest.fixture
def active_pi(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    executable = bin_dir / "pi"
    executable.write_text(_FAKE_ACTIVE_PI, encoding="utf-8")
    executable.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    return executable


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        conversations_dir=tmp_path / "conversations",
        workspace_dir=tmp_path / "workspace",
    )


async def _wait_for_path(path: Path) -> None:
    deadline = time.monotonic() + 2
    while not path.exists() and time.monotonic() < deadline:
        await asyncio.sleep(0.01)
    assert path.exists()


@pytest.mark.anyio
async def test_http_message_is_idempotent_and_cancel_settles_process(
    active_pi: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record_path = tmp_path / "http-record.json"
    monkeypatch.setenv("FAKE_PI_RECORD", str(record_path))
    app = create_app(_settings(tmp_path))
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        async with app.router.lifespan_context(app):
            created = await client.post(
                "/api/conversations",
                json={"working_dir": "http-work"},
            )
            conversation_id = created.json()["id"]
            await client.post(
                f"/api/conversations/{conversation_id}/events",
                json={"content": "start"},
            )
            run_task = asyncio.create_task(
                client.post(f"/api/conversations/{conversation_id}/run")
            )
            await _wait_for_path(record_path.with_suffix(".ready"))

            first = await client.post(
                f"/api/conversations/{conversation_id}/messages",
                json={"id": "client-1", "content": "change direction"},
            )
            duplicate = await client.post(
                f"/api/conversations/{conversation_id}/messages",
                json={"id": "client-1", "content": "change direction"},
            )
            conflict = await client.post(
                f"/api/conversations/{conversation_id}/messages",
                json={"id": "client-1", "content": "different"},
            )
            second = await client.post(
                f"/api/conversations/{conversation_id}/messages",
                json={"id": "client-2", "content": "then verify tests"},
            )
            lookup = await client.get(
                f"/api/conversations/{conversation_id}/messages/client-1"
            )
            cancelled = await client.post(
                f"/api/conversations/{conversation_id}/cancel"
            )
            run_response = await run_task
            duplicate_cancel = await client.post(
                f"/api/conversations/{conversation_id}/cancel"
            )
            too_late = await client.post(
                f"/api/conversations/{conversation_id}/messages",
                json={"id": "client-3", "content": "too late"},
            )

    assert first.status_code == duplicate.status_code == 200
    assert second.status_code == 200
    assert first.json() == duplicate.json() == lookup.json()
    assert first.json()["status"] == MessageDeliveryStatus.DELIVERED
    assert conflict.status_code == 409
    assert cancelled.json()["status"] == ConversationStatus.CANCELLED
    assert duplicate_cancel.json() == cancelled.json()
    assert run_response.json()["status"] == ConversationStatus.CANCELLED
    assert too_late.status_code == 409
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert [item["message"] for item in record["steers"]] == [
        "change direction",
        "then verify tests",
    ]
    assert record["abort"]["type"] == "abort"


def test_websocket_can_steer_and_cancel_active_rpc_process(
    active_pi: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record_path = tmp_path / "socket-record.json"
    monkeypatch.setenv("FAKE_PI_RECORD", str(record_path))
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        created = client.post(
            "/api/conversations",
            json={"working_dir": "socket-work"},
        )
        conversation_id = created.json()["id"]
        with client.websocket_connect(f"/sockets/events/{conversation_id}") as socket:
            socket.send_json({"type": "message", "content": "start"})
            deadline = time.monotonic() + 2
            while (
                not record_path.with_suffix(".ready").exists()
                and time.monotonic() < deadline
            ):
                time.sleep(0.01)
            assert record_path.with_suffix(".ready").exists()

            socket.send_json(
                {"type": "steer", "id": "socket-1", "content": "steer now"}
            )
            frames = [socket.receive_json() for _ in range(4)]
            receipt = next(
                frame for frame in frames if frame.get("type") == "message_receipt"
            )
            assert receipt["receipt"]["status"] == MessageDeliveryStatus.DELIVERED

            socket.send_json({"type": "cancel"})
            cancelled = socket.receive_json()
            assert cancelled["type"] == "cancelled"
            assert cancelled["conversation"]["status"] == ConversationStatus.CANCELLED

    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert [item["message"] for item in record["steers"]] == ["steer now"]
