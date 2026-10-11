from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from gg.sdk import (
    ConversationRecord,
    ConversationStatus,
    Event,
    EventKind,
    PiAgentConfig,
)
from gg.server.agent import (
    EventLog,
    load_base_state,
    load_meta,
    save_base_state,
    save_meta,
)
from gg.server.sqlite_state import SandboxState


def test_event_log_append_and_list(tmp_path: Path) -> None:
    log = EventLog(tmp_path / "conv-1")
    event = Event(seq=1, kind=EventKind.MESSAGE, payload={"text": "hi"})

    log.append(event)

    assert (tmp_path / "sandbox.db").exists()
    assert not list((tmp_path / "conv-1").rglob("*.json"))

    events = log.list()
    assert len(events) == 1
    assert events[0].id == event.id
    assert events[0].seq == 1
    assert events[0].kind == EventKind.MESSAGE
    assert events[0].payload == {"text": "hi"}


def test_event_log_survives_restart(tmp_path: Path) -> None:
    conv_dir = tmp_path / "conv-1"
    first = EventLog(conv_dir)
    first.append(Event(seq=2, kind=EventKind.ACTION, payload={"tool": "write_file"}))
    first.append(Event(seq=1, kind=EventKind.MESSAGE, payload={"text": "go"}))

    second = EventLog(conv_dir)
    events = second.list()

    assert [event.seq for event in events] == [1, 2]
    assert events[0].kind == EventKind.MESSAGE
    assert events[1].kind == EventKind.ACTION


def test_meta_round_trip(tmp_path: Path) -> None:
    conv_dir = tmp_path / "conv-1"
    record = ConversationRecord(
        id="conv-123",
        status=ConversationStatus.IDLE,
        working_dir="/tmp/work",
        created_at=datetime(2026, 8, 21, 12, 0, tzinfo=UTC),
    )

    save_meta(conv_dir, record)
    loaded = load_meta(conv_dir)

    assert loaded == record


def test_base_state_round_trip(tmp_path: Path) -> None:
    conv_dir = tmp_path / "conv-1"

    save_base_state(
        conv_dir,
        status=ConversationStatus.RUNNING,
        working_dir="/tmp/work",
    )
    loaded = load_base_state(conv_dir)

    assert loaded.status == ConversationStatus.RUNNING
    assert loaded.working_dir == "/tmp/work"
    assert loaded.agent == PiAgentConfig()


def test_base_state_round_trips_pi_config_without_credentials(tmp_path: Path) -> None:
    conv_dir = tmp_path / "conv-1"
    agent = PiAgentConfig(model="test/model", timeout_seconds=12)

    save_base_state(
        conv_dir,
        status=ConversationStatus.IDLE,
        working_dir="/tmp/work",
        agent=agent,
    )

    with SandboxState(tmp_path / "sandbox.db").connection() as connection:
        raw = connection.execute("SELECT base_json FROM conversations").fetchone()[0]
    assert load_base_state(conv_dir).agent == agent
    assert "test/model" in raw
    assert "credential" not in raw
    assert "api_key" not in raw


def test_json_state_is_not_a_source_of_truth(tmp_path: Path) -> None:
    import pytest

    conv_dir = tmp_path / "conv-1"
    conv_dir.mkdir()
    (conv_dir / "base_state.json").write_text(
        '{"status":"idle","working_dir":"/tmp/work"}'
    )
    with pytest.raises(FileNotFoundError):
        load_base_state(conv_dir)


def test_shared_database_receipts_and_pi_files_survive_restart(tmp_path: Path) -> None:
    from gg.sdk.domain import MessageDeliveryStatus, MessageReceipt
    from gg.server.agent import MessageReceiptStore

    conv = tmp_path / "conv"
    pi_dir = conv / "pi"
    pi_dir.mkdir(parents=True)
    (pi_dir / "session.jsonl").write_text("native pi data")
    receipt = MessageReceipt(
        id="../message", content="go", status=MessageDeliveryStatus.ACCEPTED
    )
    MessageReceiptStore(conv).save(receipt)
    assert MessageReceiptStore(conv).load(receipt.id) == receipt
    assert (pi_dir / "session.jsonl").read_text() == "native pi data"
    with SandboxState(tmp_path / "sandbox.db").connection() as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 10000
        assert connection.execute("PRAGMA synchronous").fetchone()[0] == 2


def test_process_crash_rolls_back_inflight_write_and_preserves_committed_state(
    tmp_path,
):
    import subprocess
    import sys

    conv = tmp_path / "conv"
    save_meta(
        conv,
        ConversationRecord(
            id="conv",
            status=ConversationStatus.IDLE,
            working_dir=str(tmp_path / "project"),
        ),
    )
    child = """
import os, sys
from pathlib import Path
from gg.server.agent import EventLog
from gg.sdk import Event, EventKind
conv = Path(sys.argv[1])
log = EventLog(conv)
log.append(Event(seq=1, kind=EventKind.MESSAGE, payload={"text": "committed"}))
with log.store.write() as connection:
    connection.execute("DELETE FROM events")
    os._exit(7)
"""
    result = subprocess.run([sys.executable, "-c", child, str(conv)], check=False)
    assert result.returncode == 7
    assert load_meta(conv).id == "conv"
    assert EventLog(conv).list()[0].payload == {"text": "committed"}
