"""Storage bounds, admission pressure, retention, and evidence truncation."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from gg.sdk.domain import Event
from gg.sdk.task_execution import TaskResultManifest


if TYPE_CHECKING:
    from gg.runtime.config import RuntimeSettings
    from gg.runtime.ledger import TaskLedger

TRUNCATION_SUFFIX = "\n[truncated by storage policy]"


@dataclass(frozen=True)
class StorageLimits:
    terminal_retention: timedelta
    tombstone_retention: timedelta
    max_log_evidence_bytes: int
    max_artifact_bytes: int
    max_total_evidence_bytes: int
    min_free_disk_bytes: int
    evidence_dir: Path | None

    @classmethod
    def from_settings(cls, settings: RuntimeSettings) -> StorageLimits:
        return cls(
            terminal_retention=timedelta(days=settings.terminal_retention_days),
            tombstone_retention=timedelta(days=settings.tombstone_retention_days),
            max_log_evidence_bytes=settings.max_log_evidence_bytes,
            max_artifact_bytes=settings.max_artifact_bytes,
            max_total_evidence_bytes=settings.max_total_evidence_bytes,
            min_free_disk_bytes=settings.min_free_disk_bytes,
            evidence_dir=(
                None
                if settings.task_evidence_dir is None
                else Path(settings.task_evidence_dir)
            ),
        )


@dataclass(frozen=True)
class StoragePressure:
    blocked: bool
    reason: str | None = None


@dataclass(frozen=True)
class TaskEvidenceBytes:
    log_bytes: int
    artifact_bytes: int

    @property
    def total(self) -> int:
        return self.log_bytes + self.artifact_bytes


def _truncate_text(text: str, limit: int) -> tuple[str, bool]:
    if len(text.encode("utf-8")) <= limit:
        return text, False
    encoded = text.encode("utf-8")[: max(0, limit - 64)]
    trimmed = encoded.decode("utf-8", errors="ignore")
    return trimmed + TRUNCATION_SUFFIX, True


def truncate_event_json(
    event: Event, *, max_task_log_bytes: int, current_log_bytes: int
) -> tuple[str, bool]:
    """Return serialized event JSON respecting per-task log bounds."""

    remaining = max(0, max_task_log_bytes - current_log_bytes)
    if remaining <= 0:
        stub = Event(
            seq=event.seq,
            kind=event.kind,
            payload={"storage": "event omitted; per-task log cap reached"},
        )
        return stub.model_dump_json(), True
    payload = dict(event.payload)
    serialized = event.model_dump_json()
    if len(serialized.encode("utf-8")) <= remaining:
        return serialized, False
    for key in sorted(payload, key=lambda item: len(str(payload[item])), reverse=True):
        if not isinstance(payload[key], str):
            continue
        payload[key], _ = _truncate_text(payload[key], max(256, remaining // 4))
        candidate = event.model_copy(update={"payload": payload})
        serialized = candidate.model_dump_json()
        if len(serialized.encode("utf-8")) <= remaining:
            return serialized, True
    stub = Event(
        seq=event.seq,
        kind=event.kind,
        payload={"storage": "event truncated", "detail": TRUNCATION_SUFFIX.strip()},
    )
    return stub.model_dump_json(), True


def truncate_manifest(
    manifest: TaskResultManifest, *, max_bytes: int
) -> tuple[TaskResultManifest, bool]:
    """Shrink manifest fields that dominate artifact size."""

    truncated = False
    patch = manifest.patch
    if patch is not None:
        patch, patch_truncated = _truncate_text(patch, max(4096, max_bytes // 2))
        truncated = truncated or patch_truncated
    else:
        patch_truncated = manifest.patch_truncated
    return manifest.model_copy(
        update={"patch": patch, "patch_truncated": patch_truncated or truncated}
    ), truncated


def measure_task_evidence(ledger: TaskLedger, task_id: str) -> TaskEvidenceBytes:
    return TaskEvidenceBytes(
        log_bytes=ledger.count_task_log_bytes(task_id),
        artifact_bytes=ledger.count_task_artifact_bytes(task_id),
    )


def measure_total_evidence(ledger: TaskLedger, limits: StorageLimits) -> int:
    total = ledger.count_total_evidence_bytes()
    if limits.evidence_dir is not None and limits.evidence_dir.is_dir():
        total += sum(
            path.stat().st_size
            for path in limits.evidence_dir.rglob("*")
            if path.is_file()
        )
    return total


def free_disk_bytes(*paths: Path) -> int:
    candidates = [path for path in paths if path.exists()]
    if not candidates:
        return shutil.disk_usage(Path.cwd()).free
    return min(shutil.disk_usage(path).free for path in candidates)


def admission_pressure(
    ledger: TaskLedger,
    limits: StorageLimits,
    *,
    db_path: str,
) -> StoragePressure:
    db_parent = Path(db_path).resolve().parent
    evidence_paths = [db_parent]
    if limits.evidence_dir is not None:
        evidence_paths.append(limits.evidence_dir.resolve())
    if free_disk_bytes(*evidence_paths) < limits.min_free_disk_bytes:
        return StoragePressure(
            blocked=True,
            reason=(
                f"free disk below minimum ({limits.min_free_disk_bytes} bytes required)"
            ),
        )
    if measure_total_evidence(ledger, limits) >= limits.max_total_evidence_bytes:
        return StoragePressure(
            blocked=True,
            reason=(
                f"total evidence at or above cap "
                f"({limits.max_total_evidence_bytes} bytes)"
            ),
        )
    return StoragePressure(blocked=False)


def run_retention_pass(
    ledger: TaskLedger,
    limits: StorageLimits,
    *,
    now: datetime | None = None,
) -> tuple[int, int]:
    """Expire terminal payloads and old tombstones. Returns (payloads, tombstones)."""

    moment = now or datetime.now(UTC)
    payload_cutoff = moment - limits.terminal_retention
    tombstone_cutoff = moment - limits.tombstone_retention
    payloads = ledger.expire_terminal_payloads(
        before=payload_cutoff,
        tombstone_retention=limits.tombstone_retention,
    )
    tombstones = ledger.purge_expired_tombstones(before=tombstone_cutoff)
    return payloads, tombstones


def compact_remote_effect(publication: Any | None) -> str | None:
    if publication is None:
        return None
    payload = {
        "pr_number": publication.pr_number,
        "pr_url": publication.pr_url,
        "pr_state": publication.pr_state,
        "state": publication.state.value,
    }
    return json.dumps(payload, separators=(",", ":"))


__all__ = [
    "StorageLimits",
    "StoragePressure",
    "TaskEvidenceBytes",
    "admission_pressure",
    "compact_remote_effect",
    "free_disk_bytes",
    "measure_task_evidence",
    "measure_total_evidence",
    "run_retention_pass",
    "truncate_event_json",
    "truncate_manifest",
]
