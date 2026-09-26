from __future__ import annotations

import json
import os
import queue
import re
import shutil
import signal
import subprocess
import threading
import time
from collections.abc import Callable, Mapping
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, PositiveFloat

from gg.sdk.agent_backend import DEFAULT_PI_MODEL
from gg.sdk.domain import EventKind
from gg.server.agent.agent_backend import EventEmitter
from gg.server.agent.exceptions import (
    AgentCancelledError,
    AgentControlError,
    AgentProcessError,
    AgentPromptError,
    AgentProtocolError,
    AgentStartupError,
    AgentTimeoutError,
)
from gg.server.agent.local_workspace import LocalWorkspace


_STDERR_LIMIT = 16 * 1024
_STDOUT_RECORD_LIMIT = 1024 * 1024
_EOF = object()


class PiAgentSettings(BaseModel):
    """Configuration for one headless Pi RPC run."""

    model_config = ConfigDict(frozen=True)

    provider: Literal["openrouter"] = "openrouter"
    model: str = DEFAULT_PI_MODEL
    timeout_seconds: PositiveFloat = 600
    command_ack_timeout_seconds: PositiveFloat = 5
    cancel_grace_seconds: PositiveFloat = 5


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
        self._state_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._pending_lock = threading.Lock()
        self._pending: dict[str, queue.Queue[dict[str, Any]]] = {}
        self._process: subprocess.Popen[bytes] | None = None
        self._active = False
        self._settling_listener: Callable[[], None] | None = None
        self._cancel_requested = threading.Event()

    def set_settling_listener(self, listener: Callable[[], None] | None) -> None:
        with self._state_lock:
            self._settling_listener = listener

    def steer(self, message: str) -> tuple[bool, str | None]:
        """Queue a steering message and wait only for Pi's queue acknowledgement."""
        request_id = f"gg-steer-{uuid4()}"
        waiter: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
        with self._state_lock:
            process = self._process
            if not self._active or process is None or process.poll() is not None:
                raise AgentControlError("Pi is no longer accepting steering messages")
            with self._pending_lock:
                self._pending[request_id] = waiter
            try:
                self._send(
                    process,
                    {"id": request_id, "type": "steer", "message": message},
                )
            except Exception:
                with self._pending_lock:
                    self._pending.pop(request_id, None)
                raise
        try:
            response = waiter.get(timeout=self.settings.command_ack_timeout_seconds)
        except queue.Empty as exc:
            raise AgentProcessError(
                "Pi steering acknowledgement was lost; delivery is unknown"
            ) from exc
        finally:
            with self._pending_lock:
                self._pending.pop(request_id, None)
        return self._control_response(response, command="steer")

    def cancel(self) -> None:
        """Abort Pi, then close and terminate its isolated process group."""
        with self._state_lock:
            process = self._process
            if not self._active or process is None:
                raise AgentControlError("Pi has no active process to cancel")
            self._cancel_requested.set()
            if process.poll() is not None:
                return
        request_id = f"gg-abort-{uuid4()}"
        waiter: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
        with self._pending_lock:
            self._pending[request_id] = waiter
        try:
            self._send(process, {"id": request_id, "type": "abort"})
            try:
                response = waiter.get(timeout=self.settings.command_ack_timeout_seconds)
                try:
                    self._control_response(response, command="abort")
                except AgentProtocolError:
                    pass
            except queue.Empty:
                # Cancellation does not depend on the acknowledgement: process
                # teardown below is the confirmation boundary.
                pass
        except AgentProcessError:
            pass
        finally:
            with self._pending_lock:
                self._pending.pop(request_id, None)
        self._close_stdin(process)
        self._terminate_process_tree(
            process,
            grace_seconds=self.settings.cancel_grace_seconds,
        )

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
                start_new_session=True,
            )
        except OSError as exc:
            raise AgentStartupError("Pi RPC process could not be started") from exc

        with self._state_lock:
            if self._active:
                process.kill()
                process.wait()
                raise AgentControlError("Pi backend already owns an active process")
            self._process = process
            self._active = True
            self._cancel_requested.clear()

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
            self._mark_settling()
            self._stop_process(process, abort=timed_out)
            stdout_thread.join(timeout=1.0)
            stderr_thread.join(timeout=1.0)
            with self._state_lock:
                self._process = None

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
                if self._cancel_requested.is_set():
                    raise AgentCancelledError("Pi run was cancelled")
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
            if message_type == "response" and self._route_control_response(item):
                continue
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
                self._mark_settling()
                if self._cancel_requested.is_set():
                    raise AgentCancelledError("Pi run was cancelled")
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

    def _send(
        self,
        process: subprocess.Popen[bytes],
        message: Mapping[str, Any],
    ) -> None:
        if process.stdin is None:
            raise AgentProcessError("Pi stdin is unavailable")
        try:
            with self._write_lock:
                process.stdin.write(json.dumps(message, separators=(",", ":")).encode())
                process.stdin.write(b"\n")
                process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise AgentProcessError("Pi exited before accepting the command") from exc

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

    def _stop_process(
        self,
        process: subprocess.Popen[bytes],
        *,
        abort: bool,
    ) -> None:
        if process.poll() is None and abort:
            try:
                self._send(
                    process,
                    {"id": f"gg-abort-{uuid4()}", "type": "abort"},
                )
            except AgentProcessError:
                pass
        self._close_stdin(process)
        if process.poll() is not None:
            return
        try:
            process.wait(timeout=self.settings.cancel_grace_seconds)
            return
        except subprocess.TimeoutExpired:
            self._signal_process_group(process, signal.SIGTERM)
        try:
            process.wait(timeout=self.settings.cancel_grace_seconds)
            return
        except subprocess.TimeoutExpired:
            self._signal_process_group(process, signal.SIGKILL)
            process.wait()

    @staticmethod
    def _close_stdin(process: subprocess.Popen[bytes]) -> None:
        if process.stdin is not None:
            try:
                process.stdin.close()
            except OSError:
                pass

    @classmethod
    def _terminate_process_tree(
        cls,
        process: subprocess.Popen[bytes],
        *,
        grace_seconds: float,
    ) -> None:
        if process.poll() is None:
            try:
                process.wait(timeout=grace_seconds)
            except subprocess.TimeoutExpired:
                pass

        # The RPC parent may exit on EOF while a tool subprocess remains.
        # Signal the session's process group even after the parent has exited.
        cls._signal_process_group(process, signal.SIGTERM)
        deadline = time.monotonic() + grace_seconds
        while cls._process_group_exists(process.pid) and time.monotonic() < deadline:
            time.sleep(min(0.01, grace_seconds))
        if cls._process_group_exists(process.pid):
            cls._signal_process_group(process, signal.SIGKILL)
        if process.poll() is None:
            process.wait()

    @staticmethod
    def _signal_process_group(process: subprocess.Popen[bytes], sig: int) -> None:
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            return

    @staticmethod
    def _process_group_exists(process_group_id: int) -> bool:
        try:
            os.killpg(process_group_id, 0)
        except ProcessLookupError:
            return False
        return True

    def _route_control_response(self, response: dict[str, Any]) -> bool:
        request_id = response.get("id")
        if not isinstance(request_id, str):
            return False
        with self._pending_lock:
            waiter = self._pending.get(request_id)
        if waiter is None:
            return False
        try:
            waiter.put_nowait(response)
        except queue.Full:
            pass
        return True

    @classmethod
    def _control_response(
        cls,
        response: Mapping[str, Any],
        *,
        command: str,
    ) -> tuple[bool, str | None]:
        if response.get("command") != command:
            raise AgentProtocolError(f"Pi returned a different command for {command}")
        if response.get("success") is True:
            return True, None
        return False, f"Pi rejected {command}"

    def _mark_settling(self) -> None:
        with self._state_lock:
            if not self._active:
                return
            listener = self._settling_listener
        if listener is not None:
            listener()
        with self._state_lock:
            self._active = False

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
