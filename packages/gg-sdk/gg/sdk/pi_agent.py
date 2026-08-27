from __future__ import annotations

import json
import os
import queue
import re
import shutil
import subprocess
import threading
import time
from collections.abc import Mapping
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, PositiveFloat

from gg.sdk.agent_backend import EventEmitter
from gg.sdk.domain import EventKind
from gg.sdk.exceptions import (
    AgentProcessError,
    AgentPromptError,
    AgentProtocolError,
    AgentStartupError,
    AgentTimeoutError,
)
from gg.sdk.local_workspace import LocalWorkspace


_STDERR_LIMIT = 16 * 1024
_STDOUT_RECORD_LIMIT = 1024 * 1024
_SHUTDOWN_GRACE_SECONDS = 5.0
_EOF = object()


class PiAgentSettings(BaseModel):
    """Configuration for one headless Pi RPC run."""

    model_config = ConfigDict(frozen=True)

    provider: Literal["openrouter"] = "openrouter"
    model: str = "google/gemini-3.7-flash"
    timeout_seconds: PositiveFloat = 600


class _BoundedCapture:
    def __init__(self, limit: int) -> None:
        self._limit = limit
        self._data = bytearray()
        self._lock = threading.Lock()

    def append(self, chunk: bytes) -> None:
        with self._lock:
            self._data.extend(chunk)
            overflow = len(self._data) - self._limit
            if overflow > 0:
                del self._data[:overflow]

    def text(self) -> str:
        with self._lock:
            return bytes(self._data).decode("utf-8", errors="replace")


class PiRpcAgent:
    """Run one Pi turn over its strict JSONL stdio protocol."""

    def __init__(self, settings: PiAgentSettings | None = None) -> None:
        self.settings = settings or PiAgentSettings()

    def run(
        self,
        prompt: str,
        workspace: LocalWorkspace,
        emit: EventEmitter,
    ) -> None:
        api_key = self._preflight()
        command = [
            "pi",
            "--mode",
            "rpc",
            "--no-session",
            "--no-approve",
            "--provider",
            self.settings.provider,
            "--model",
            self.settings.model,
        ]
        try:
            process = subprocess.Popen(
                command,
                cwd=workspace.working_dir,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except OSError as exc:
            raise AgentStartupError("Pi RPC process could not be started") from exc

        messages: queue.Queue[object] = queue.Queue()
        stderr = _BoundedCapture(_STDERR_LIMIT)
        stdout_thread = threading.Thread(
            target=self._read_stdout,
            args=(process, messages),
            daemon=True,
            name="pi-rpc-stdout",
        )
        stderr_thread = threading.Thread(
            target=self._drain_stderr,
            args=(process, stderr),
            daemon=True,
            name="pi-rpc-stderr",
        )
        stdout_thread.start()
        stderr_thread.start()

        timed_out = False
        try:
            request_id = f"gg-prompt-{uuid4()}"
            self._send(
                process,
                {"id": request_id, "type": "prompt", "message": prompt},
            )
            self._consume(
                process,
                messages,
                request_id=request_id,
                emit=emit,
                api_key=api_key,
                stderr=stderr,
            )
        except AgentTimeoutError:
            timed_out = True
            raise
        finally:
            self._stop_process(process, abort=timed_out)
            stdout_thread.join(timeout=1.0)
            stderr_thread.join(timeout=1.0)

    def _preflight(self) -> str:
        if shutil.which("pi") is None:
            raise AgentStartupError("Pi executable was not found on PATH")
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise AgentStartupError("OPENROUTER_API_KEY is required for Pi")
        return api_key

    def _consume(
        self,
        process: subprocess.Popen[bytes],
        messages: queue.Queue[object],
        *,
        request_id: str,
        emit: EventEmitter,
        api_key: str,
        stderr: _BoundedCapture,
    ) -> None:
        deadline = time.monotonic() + self.settings.timeout_seconds
        prompt_accepted = False

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AgentTimeoutError(
                    f"Pi did not settle within {self.settings.timeout_seconds} seconds"
                )
            try:
                item = messages.get(timeout=remaining)
            except queue.Empty as exc:
                raise AgentTimeoutError(
                    f"Pi did not settle within {self.settings.timeout_seconds} seconds"
                ) from exc

            if item is _EOF:
                return_code = process.poll()
                detail = self._sanitize(stderr.text(), api_key)
                message = f"Pi exited before agent_settled (exit code {return_code})"
                if detail:
                    message = f"{message}: {detail}"
                raise AgentProcessError(message)
            if isinstance(item, AgentProtocolError):
                raise item
            if not isinstance(item, dict):
                raise AgentProtocolError("Pi emitted a non-object JSON message")

            message_type = item.get("type")
            if message_type == "response" and item.get("id") == request_id:
                if item.get("command") != "prompt":
                    raise AgentProtocolError(
                        "Pi returned the prompt id for a different command"
                    )
                if item.get("success") is not True:
                    detail = self._response_error(item, api_key)
                    raise AgentPromptError(f"Pi rejected the prompt{detail}")
                prompt_accepted = True
                continue

            if message_type == "agent_settled":
                if not prompt_accepted:
                    raise AgentProtocolError(
                        "Pi settled before accepting the correlated prompt"
                    )
                return

            self._translate_event(item, emit=emit, api_key=api_key)

    def _translate_event(
        self,
        message: dict[str, Any],
        *,
        emit: EventEmitter,
        api_key: str,
    ) -> None:
        message_type = message.get("type")
        if message_type == "message_end":
            completed = self._mapping_field(message, "message")
            if completed.get("role") != "assistant":
                return
            if completed.get("stopReason") == "error":
                detail = self._sanitize(str(completed.get("errorMessage", "")), api_key)
                suffix = f": {detail}" if detail else ""
                raise AgentProcessError(f"Pi assistant failed{suffix}")
            emit(
                EventKind.MESSAGE,
                {"role": "assistant", "text": self._assistant_text(completed)},
            )
        elif message_type == "tool_execution_start":
            emit(
                EventKind.ACTION,
                {
                    "tool_call_id": self._string_field(message, "toolCallId"),
                    "tool": self._string_field(message, "toolName"),
                    "args": message.get("args"),
                },
            )
        elif message_type == "tool_execution_end":
            is_error = message.get("isError")
            if not isinstance(is_error, bool):
                raise AgentProtocolError("Pi tool result has invalid isError")
            emit(
                EventKind.OBSERVATION,
                {
                    "tool_call_id": self._string_field(message, "toolCallId"),
                    "tool": self._string_field(message, "toolName"),
                    "result": message.get("result"),
                    "is_error": is_error,
                },
            )

    @staticmethod
    def _assistant_text(message: Mapping[str, Any]) -> str:
        content = message.get("content")
        if isinstance(content, str):
            return content
        if not isinstance(content, list):
            raise AgentProtocolError("Pi assistant message has invalid content")

        parts: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                raise AgentProtocolError("Pi assistant content block is not an object")
            if block.get("type") == "text":
                text = block.get("text")
                if not isinstance(text, str):
                    raise AgentProtocolError("Pi assistant text block is invalid")
                parts.append(text)
        return "".join(parts)

    @staticmethod
    def _mapping_field(message: Mapping[str, Any], name: str) -> dict[str, Any]:
        value = message.get(name)
        if not isinstance(value, dict):
            raise AgentProtocolError(f"Pi message has invalid {name}")
        return value

    @staticmethod
    def _string_field(message: Mapping[str, Any], name: str) -> str:
        value = message.get(name)
        if not isinstance(value, str):
            raise AgentProtocolError(f"Pi message has invalid {name}")
        return value

    @staticmethod
    def _send(process: subprocess.Popen[bytes], message: Mapping[str, Any]) -> None:
        if process.stdin is None:
            raise AgentProcessError("Pi stdin is unavailable")
        try:
            process.stdin.write(json.dumps(message, separators=(",", ":")).encode())
            process.stdin.write(b"\n")
            process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise AgentProcessError("Pi exited before accepting the prompt") from exc

    @classmethod
    def _read_stdout(
        cls,
        process: subprocess.Popen[bytes],
        messages: queue.Queue[object],
    ) -> None:
        if process.stdout is None:
            messages.put(AgentProtocolError("Pi stdout is unavailable"))
            messages.put(_EOF)
            return

        buffer = bytearray()
        try:
            while chunk := process.stdout.read1(4096):
                buffer.extend(chunk)
                while True:
                    newline = buffer.find(b"\n")
                    if newline < 0:
                        if len(buffer) > _STDOUT_RECORD_LIMIT:
                            raise AgentProtocolError("Pi JSONL record is too large")
                        break
                    record = bytes(buffer[:newline])
                    del buffer[: newline + 1]
                    if record.endswith(b"\r"):
                        record = record[:-1]
                    messages.put(cls._decode_record(record))
            if buffer:
                raise AgentProtocolError("Pi emitted an unterminated JSONL record")
        except AgentProtocolError as exc:
            messages.put(exc)
        except OSError:
            messages.put(AgentProtocolError("Pi stdout could not be read"))
        finally:
            messages.put(_EOF)

    @staticmethod
    def _decode_record(record: bytes) -> dict[str, Any]:
        try:
            decoded = record.decode("utf-8")
            message = json.loads(decoded)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AgentProtocolError("Pi emitted malformed JSONL") from exc
        if not isinstance(message, dict):
            raise AgentProtocolError("Pi emitted a non-object JSON message")
        return message

    @staticmethod
    def _drain_stderr(
        process: subprocess.Popen[bytes],
        capture: _BoundedCapture,
    ) -> None:
        if process.stderr is None:
            return
        try:
            while chunk := process.stderr.read1(4096):
                capture.append(chunk)
        except OSError:
            return

    @classmethod
    def _stop_process(
        cls,
        process: subprocess.Popen[bytes],
        *,
        abort: bool,
    ) -> None:
        if process.poll() is None and abort:
            try:
                cls._send(process, {"id": f"gg-abort-{uuid4()}", "type": "abort"})
            except AgentProcessError:
                pass
        if process.stdin is not None:
            try:
                process.stdin.close()
            except OSError:
                pass
        if process.poll() is not None:
            return
        try:
            process.wait(timeout=_SHUTDOWN_GRACE_SECONDS)
            return
        except subprocess.TimeoutExpired:
            process.terminate()
        try:
            process.wait(timeout=_SHUTDOWN_GRACE_SECONDS)
            return
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

    @classmethod
    def _response_error(cls, response: Mapping[str, Any], api_key: str) -> str:
        raw = response.get("error")
        if not isinstance(raw, str):
            return ""
        detail = cls._sanitize(raw, api_key)
        return f": {detail}" if detail else ""

    @staticmethod
    def _sanitize(value: str, api_key: str) -> str:
        sanitized = value.replace(api_key, "[REDACTED]")
        sanitized = re.sub(
            r"(?i)(api[_-]?key\s*[:=]\s*)\S+",
            r"\1[REDACTED]",
            sanitized,
        )
        return " ".join(sanitized.split())[:2000]
