from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

import gg.sdk.pi_agent as pi_agent
from gg.sdk import (
    AgentProcessError,
    AgentPromptError,
    AgentProtocolError,
    AgentStartupError,
    AgentTimeoutError,
    ConversationStatus,
    EventKind,
    LocalConversation,
    LocalWorkspace,
    PiAgentSettings,
    PiRpcAgent,
)


_FAKE_PI = r'''#!/usr/bin/env python3
import json
import os
import sys


mode = os.environ.get("FAKE_PI_MODE", "success")
record_path = os.environ.get("FAKE_PI_RECORD")


def send(message, *, crlf=False):
    ending = b"\r\n" if crlf else b"\n"
    sys.stdout.buffer.write(json.dumps(message).encode() + ending)
    sys.stdout.buffer.flush()


def record(data):
    if record_path:
        with open(record_path, "w", encoding="utf-8") as stream:
            json.dump(data, stream)


prompt = json.loads(sys.stdin.buffer.readline())
state = {"argv": sys.argv, "cwd": os.getcwd(), "prompt": prompt}

if mode == "rejected":
    send({
        "id": prompt["id"],
        "type": "response",
        "command": "prompt",
        "success": False,
        "error": "bad API_KEY=" + os.environ["OPENROUTER_API_KEY"],
    })
elif mode == "malformed":
    sys.stdout.buffer.write(b'{"type":oops}\n')
    sys.stdout.buffer.flush()
elif mode == "unterminated":
    sys.stdout.buffer.write(b'{"type":"agent_settled"}\r')
    sys.stdout.buffer.flush()
elif mode == "early_exit":
    sys.stderr.write("failure OPENROUTER_API_KEY=" + os.environ["OPENROUTER_API_KEY"])
    sys.stderr.flush()
    sys.exit(7)
elif mode == "timeout":
    send({
        "id": prompt["id"],
        "type": "response",
        "command": "prompt",
        "success": True,
    })
    abort = json.loads(sys.stdin.buffer.readline())
    state["abort"] = abort
    record(state)
else:
    if mode == "noisy":
        sys.stderr.write("x" * (1024 * 1024))
        sys.stderr.flush()
    send({
        "id": prompt["id"],
        "type": "response",
        "command": "prompt",
        "success": True,
    }, crlf=True)
    send({"type": "message_update", "delta": "ignored"})
    send({
        "type": "message_end",
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": "done\u2028now"}],
        },
    })
    send({
        "type": "tool_execution_start",
        "toolCallId": "call-1",
        "toolName": "write",
        "args": {"path": "PI_NOTES.md"},
    })
    send({"type": "tool_execution_update", "partialResult": "ignored"})
    send({
        "type": "tool_execution_end",
        "toolCallId": "call-1",
        "toolName": "write",
        "result": {"content": "ok"},
        "isError": False,
    })
    send({"type": "agent_end"})
    send({"type": "agent_settled"})
    record(state)
    if mode == "hold_until_eof":
        sys.stdin.buffer.read()
        Path = __import__("pathlib").Path
        Path(record_path + ".cleaned").write_text("clean", encoding="utf-8")
'''


@pytest.fixture
def fake_pi(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    executable = bin_dir / "pi"
    executable.write_text(_FAKE_PI, encoding="utf-8")
    executable.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-secret")
    return executable


def _conversation(
    tmp_path: Path,
    *,
    timeout_seconds: float = 2,
) -> LocalConversation:
    return LocalConversation(
        conversation_dir=tmp_path / "conversation",
        workspace=LocalWorkspace(working_dir=tmp_path / "workspace"),
        agent_backend=PiRpcAgent(
            PiAgentSettings(timeout_seconds=timeout_seconds),
        ),
    )


def _run_and_capture_error(
    tmp_path: Path,
    error_type: type[Exception],
    *,
    timeout_seconds: float = 2,
) -> tuple[LocalConversation, Exception]:
    conversation = _conversation(tmp_path, timeout_seconds=timeout_seconds)
    conversation.send_message("do the work")
    with pytest.raises(error_type) as caught:
        conversation.run()
    return conversation, caught.value


def test_pi_settings_fix_provider_and_supply_defaults() -> None:
    settings = PiAgentSettings()

    assert settings.provider == "openrouter"
    assert settings.model == "google/gemini-3.7-flash"
    assert settings.timeout_seconds == 600
    with pytest.raises(ValidationError):
        PiAgentSettings(provider="another-provider")  # type: ignore[arg-type]


def test_success_uses_expected_command_cwd_and_translates_final_events(
    fake_pi: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record_path = tmp_path / "record.json"
    monkeypatch.setenv("FAKE_PI_RECORD", str(record_path))
    conversation = _conversation(tmp_path)
    conversation.send_message("write the file")

    conversation.run()

    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["argv"] == [
        str(fake_pi),
        "--mode",
        "rpc",
        "--no-session",
        "--no-approve",
        "--provider",
        "openrouter",
        "--model",
        "google/gemini-3.7-flash",
    ]
    assert record["cwd"] == str(tmp_path / "workspace")
    assert record["prompt"]["type"] == "prompt"
    assert record["prompt"]["message"] == "write the file"
    assert record["prompt"]["id"].startswith("gg-prompt-")

    events = conversation.list_events()
    assert [event.kind for event in events] == [
        EventKind.MESSAGE,
        EventKind.STATUS,
        EventKind.MESSAGE,
        EventKind.ACTION,
        EventKind.OBSERVATION,
        EventKind.STATUS,
    ]
    assert events[2].payload == {"role": "assistant", "text": "done\u2028now"}
    assert events[3].payload == {
        "tool_call_id": "call-1",
        "tool": "write",
        "args": {"path": "PI_NOTES.md"},
    }
    assert events[4].payload == {
        "tool_call_id": "call-1",
        "tool": "write",
        "result": {"content": "ok"},
        "is_error": False,
    }
    assert events[-1].payload == {"status": ConversationStatus.FINISHED}


def test_missing_binary_fails_clearly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PATH", "")
    monkeypatch.setenv("OPENROUTER_API_KEY", "must-not-appear")

    conversation, error = _run_and_capture_error(tmp_path, AgentStartupError)

    assert "Pi executable" in str(error)
    _assert_persisted_error(conversation, "agent_startup_error", "must-not-appear")


def test_missing_key_fails_clearly(
    fake_pi: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY")

    conversation, error = _run_and_capture_error(tmp_path, AgentStartupError)

    assert "OPENROUTER_API_KEY is required" in str(error)
    _assert_persisted_error(conversation, "agent_startup_error", "secret")


def test_rejected_prompt_is_typed_and_sanitized(
    fake_pi: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FAKE_PI_MODE", "rejected")

    conversation, error = _run_and_capture_error(tmp_path, AgentPromptError)

    assert "test-openrouter-secret" not in str(error)
    _assert_persisted_error(
        conversation,
        "agent_prompt_error",
        "test-openrouter-secret",
    )


@pytest.mark.parametrize("mode", ["malformed", "unterminated"])
def test_malformed_or_non_lf_json_is_a_protocol_error(
    fake_pi: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    monkeypatch.setenv("FAKE_PI_MODE", mode)

    conversation, _ = _run_and_capture_error(tmp_path, AgentProtocolError)

    _assert_persisted_error(
        conversation,
        "agent_protocol_error",
        "test-openrouter-secret",
    )


def test_early_exit_is_typed_and_does_not_persist_stderr_secret(
    fake_pi: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FAKE_PI_MODE", "early_exit")

    conversation, error = _run_and_capture_error(tmp_path, AgentProcessError)

    assert "exit code 7" in str(error)
    assert "test-openrouter-secret" not in str(error)
    _assert_persisted_error(
        conversation,
        "agent_process_error",
        "test-openrouter-secret",
    )


def test_timeout_sends_correlated_abort_and_persists_error(
    fake_pi: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record_path = tmp_path / "record.json"
    monkeypatch.setenv("FAKE_PI_MODE", "timeout")
    monkeypatch.setenv("FAKE_PI_RECORD", str(record_path))

    conversation, _ = _run_and_capture_error(
        tmp_path,
        AgentTimeoutError,
        timeout_seconds=0.05,
    )

    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["abort"]["type"] == "abort"
    assert record["abort"]["id"].startswith("gg-abort-")
    _assert_persisted_error(
        conversation,
        "agent_timeout_error",
        "test-openrouter-secret",
    )


def test_stderr_is_drained_while_child_runs(
    fake_pi: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FAKE_PI_MODE", "noisy")

    conversation = _conversation(tmp_path)
    conversation.send_message("go")
    conversation.run()

    assert conversation.status == ConversationStatus.FINISHED


def test_stderr_capture_keeps_only_its_bounded_tail() -> None:
    capture = pi_agent._BoundedCapture(8)

    capture.append(b"older-output")
    capture.append(b"new-tail")

    assert capture.text() == "new-tail"


def test_successful_process_is_closed_after_settlement(
    fake_pi: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record_path = tmp_path / "record.json"
    monkeypatch.setenv("FAKE_PI_MODE", "hold_until_eof")
    monkeypatch.setenv("FAKE_PI_RECORD", str(record_path))

    conversation = _conversation(tmp_path)
    conversation.send_message("go")
    conversation.run()

    assert Path(f"{record_path}.cleaned").read_text(encoding="utf-8") == "clean"


def test_shutdown_terminates_then_kills_a_stubborn_child() -> None:
    process = _StubbornProcess()

    PiRpcAgent._stop_process(process, abort=True)  # type: ignore[arg-type]

    command = json.loads(process.stdin.getvalue().decode())
    assert command["type"] == "abort"
    assert process.terminated is True
    assert process.killed is True


class _StubbornProcess:
    def __init__(self) -> None:
        self.stdin = _NonClosingBytesIO()
        self.terminated = False
        self.killed = False

    def poll(self) -> None:
        return None

    def wait(self, timeout: float | None = None) -> int:
        if self.killed:
            return -9
        raise subprocess.TimeoutExpired("pi", timeout)

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True


class _NonClosingBytesIO:
    def __init__(self) -> None:
        self._data = bytearray()

    def write(self, value: bytes) -> None:
        self._data.extend(value)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        pass

    def getvalue(self) -> bytes:
        return bytes(self._data)


def _assert_persisted_error(
    conversation: LocalConversation,
    error_type: str,
    forbidden: str,
) -> None:
    assert conversation.status == ConversationStatus.ERROR
    events = conversation.list_events()
    assert events[-2].kind == EventKind.ERROR
    assert events[-2].payload["type"] == error_type
    assert forbidden not in json.dumps(events[-2].payload)
    assert events[-1].payload == {"status": ConversationStatus.ERROR}
