from __future__ import annotations

from pathlib import Path

from gg.sdk import EventLog
from gg.sdk.demo.write_notes import run_demo


def test_write_notes_demo_creates_notes_and_conversation_artifacts(
    tmp_path: Path,
) -> None:
    notes_path, conversation_dir = run_demo(tmp_path, message="integration test")

    assert notes_path.exists()
    assert notes_path.read_text(encoding="utf-8") == "# Notes\n\nintegration test\n"

    assert (conversation_dir / "meta.json").is_file()
    assert (conversation_dir / "base_state.json").is_file()

    event_files = list((conversation_dir / "events").glob("event-*.json"))
    assert len(event_files) >= 1

    events = EventLog(conversation_dir).list()
    assert len(events) >= 1
