from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from gg.sdk import EventKind, LocalWorkspace
from gg.sdk.agent_backend import EventEmitter
from gg.sdk.demo import pi_notes


class FakePiBackend:
    def __init__(self) -> None:
        self.prompt = ""
        self.workspace: LocalWorkspace | None = None

    def run(
        self,
        prompt: str,
        workspace: LocalWorkspace,
        emit: EventEmitter,
    ) -> None:
        self.prompt = prompt
        self.workspace = workspace
        marker = prompt.split("exact unique marker: ", 1)[1].split(".", 1)[0]
        emit(
            EventKind.ACTION,
            {"tool": "write", "args": {"path": pi_notes.NOTES_FILENAME}},
        )
        workspace.write_file(pi_notes.NOTES_FILENAME, f"Pi demo: {marker}\n")
        emit(
            EventKind.OBSERVATION,
            {"tool": "write", "result": "file written", "is_error": False},
        )
        emit(
            EventKind.MESSAGE,
            {"role": "assistant", "text": "Created PI_NOTES.md."},
        )


def test_pi_demo_runs_offline_with_fake_backend(tmp_path: Path) -> None:
    backend = FakePiBackend()

    result = pi_notes.run_demo(
        tmp_path,
        agent_backend=backend,
        marker="offline-marker-028",
    )

    assert backend.workspace is not None
    assert backend.workspace.working_dir == tmp_path
    assert "PI_NOTES.md" in backend.prompt
    assert "offline-marker-028" in backend.prompt
    assert result.workspace_path == tmp_path
    assert result.notes_path == tmp_path / "PI_NOTES.md"
    assert result.notes_content == "Pi demo: offline-marker-028\n"
    assert result.final_assistant_text == "Created PI_NOTES.md."
    assert (result.conversation_dir / "meta.json").is_file()
    assert [event.kind for event in result.events] == [
        EventKind.MESSAGE,
        EventKind.STATUS,
        EventKind.ACTION,
        EventKind.OBSERVATION,
        EventKind.MESSAGE,
        EventKind.STATUS,
    ]


def test_pi_demo_default_workspace_is_unique_and_left_on_disk(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    created = tmp_path / "temporary-workspace"
    monkeypatch.setattr(pi_notes.tempfile, "mkdtemp", lambda **_: str(created))

    result = pi_notes.run_demo(
        agent_backend=FakePiBackend(),
    )

    assert result.workspace_path == created
    assert result.notes_path.is_file()
    assert result.marker.startswith("GG_PI_DEMO_")
    assert len(result.marker) == len("GG_PI_DEMO_") + 32


def test_pi_demo_cli_prints_workspace_file_assistant_and_event_summary(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    result = pi_notes.run_demo(
        tmp_path,
        agent_backend=FakePiBackend(),
        marker="cli-marker",
    )
    monkeypatch.setattr(pi_notes, "run_demo", lambda _: result)
    monkeypatch.setattr("sys.argv", ["pi_notes", "--workspace", str(tmp_path)])

    pi_notes.main()

    output = capsys.readouterr().out
    assert f"Workspace: {tmp_path}" in output
    assert "Pi demo: cli-marker" in output
    assert "Final assistant text:\nCreated PI_NOTES.md." in output
    assert "Persisted events (6):" in output
    assert "message=2" in output


@pytest.mark.pi
@pytest.mark.skipif(
    os.getenv("GG_RUN_PI_TESTS") != "1",
    reason=(
        "set GG_RUN_PI_TESTS=1 and run uv with --no-editable to run the paid "
        "live Pi smoke test"
    ),
)
def test_live_pi_demo(tmp_path: Path) -> None:
    if shutil.which("pi") is None:
        pytest.skip("Pi executable is not installed")
    if not os.getenv("OPENROUTER_API_KEY"):
        pytest.skip("OPENROUTER_API_KEY is not configured")

    result = pi_notes.run_demo(tmp_path)

    assert result.notes_path.is_file()
    assert result.marker in result.notes_content
    assert result.final_assistant_text
