"""Atomic persistence for execution identity and result manifests."""

from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path

from gg.sdk.task_execution import (
    TaskExecutionPhase,
    TaskExecutionRecord,
    TaskResultManifest,
)


class StartKeyConflictError(Exception):
    """Raised when a start key is reused with different task identity."""


class ExecutionStore:
    """File-backed store for one sandbox supervisor process."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def admit_or_get(
        self,
        *,
        start_key: str,
        task_id: str,
        repository: str,
        task_branch: str,
        base_ref: str | None,
        deadline_at: datetime,
    ) -> tuple[TaskExecutionRecord, bool]:
        with self._lock:
            existing_id = self._read_start_key(start_key)
            if existing_id is not None:
                record = self.load_execution(existing_id)
                if (
                    record.task_id != task_id
                    or record.task_branch != task_branch
                    or record.repository != repository
                ):
                    raise StartKeyConflictError(
                        f"start_key {start_key!r} already bound to another execution"
                    )
                return record, False
            execution_id = self._new_execution_id(task_id, start_key)
            now = datetime.now(UTC)
            record = TaskExecutionRecord(
                execution_id=execution_id,
                task_id=task_id,
                repository=repository,
                start_key=start_key,
                task_branch=task_branch,
                base_ref=base_ref,
                deadline_at=deadline_at,
                created_at=now,
                updated_at=now,
            )
            self._write_execution(record)
            self._bind_start_key(start_key, execution_id)
            return record, True

    def load_execution(self, execution_id: str) -> TaskExecutionRecord:
        path = self._execution_path(execution_id)
        if not path.is_file():
            raise KeyError(f"unknown execution {execution_id}")
        return TaskExecutionRecord.model_validate_json(path.read_text(encoding="utf-8"))

    def save_execution(self, record: TaskExecutionRecord) -> None:
        with self._lock:
            self._write_execution(record)

    def save_manifest(self, manifest: TaskResultManifest) -> Path:
        path = self._manifest_path(manifest.execution_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._atomic_write(path, manifest.model_dump_json(indent=2))
        return path

    def load_manifest(self, execution_id: str) -> TaskResultManifest:
        path = self._manifest_path(execution_id)
        if not path.is_file():
            raise KeyError(f"no manifest for execution {execution_id}")
        return TaskResultManifest.model_validate_json(path.read_text(encoding="utf-8"))

    def list_non_terminal(self) -> list[TaskExecutionRecord]:
        records: list[TaskExecutionRecord] = []
        for path in sorted(self._root.glob("executions/*.json")):
            record = TaskExecutionRecord.model_validate_json(
                path.read_text(encoding="utf-8")
            )
            if record.phase not in {
                TaskExecutionPhase.COMPLETED,
                TaskExecutionPhase.FAILED,
            }:
                records.append(record)
        return records

    def _execution_path(self, execution_id: str) -> Path:
        return self._root / "executions" / f"{execution_id}.json"

    def _manifest_path(self, execution_id: str) -> Path:
        return self._root / "manifests" / f"{execution_id}.json"

    def _start_key_path(self, start_key: str) -> Path:
        digest = hashlib.sha256(start_key.encode()).hexdigest()
        return self._root / "start_keys" / f"{digest}.json"

    def _read_start_key(self, start_key: str) -> str | None:
        path = self._start_key_path(start_key)
        if not path.is_file():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload["execution_id"]

    def _bind_start_key(self, start_key: str, execution_id: str) -> None:
        path = self._start_key_path(start_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_write(path, json.dumps({"execution_id": execution_id}))

    def _write_execution(self, record: TaskExecutionRecord) -> None:
        path = self._execution_path(record.execution_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_write(path, record.model_dump_json(indent=2))

    @staticmethod
    def _new_execution_id(task_id: str, start_key: str) -> str:
        digest = hashlib.sha256(f"{task_id}:{start_key}".encode()).hexdigest()[:32]
        return digest

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, path)


__all__ = ["ExecutionStore", "StartKeyConflictError"]
