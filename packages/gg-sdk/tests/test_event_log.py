from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from gg.sdk import (
    ConversationRecord,
    ConversationStatus,
    Event,
    EventKind,
    EventLog,
    PiAgentConfig,
    load_base_state,
    load_meta,
    save_base_state,
    save_meta,
)


def test_event_log_append_and_list(tmp_path: Path) -> None:
    log = EventLog(tmp_path / "conv-1")
    event = Event(seq=1, kind=EventKind.MESSAGE, payload={"text": "hi"})

    log.append(event)

    path = tmp_path / "conv-1" / "events" / f"event-00001-{event.id}.json"
    assert path.exists()

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

    raw = (conv_dir / "base_state.json").read_text(encoding="utf-8")
    assert load_base_state(conv_dir).agent == agent
    assert "test/model" in raw
    assert "credential" not in raw
    assert "api_key" not in raw


def test_legacy_base_state_without_agent_defaults_to_pi(tmp_path: Path) -> None:
    conv_dir = tmp_path / "conv-1"
    conv_dir.mkdir()
    (conv_dir / "base_state.json").write_text(
        '{"status":"idle","working_dir":"/tmp/work"}',
        encoding="utf-8",
    )

    assert load_base_state(conv_dir).agent == PiAgentConfig()
