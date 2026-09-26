"""SQLite online backup helpers for the control-plane ledger."""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

from gg.runtime.ledger import TaskLedger


def backup_sqlite_online(*, ledger: TaskLedger, destination: Path) -> Path:
    """Copy the open WAL-mode database using SQLite's online backup API."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    ledger.online_backup(destination)
    return destination


def backup_evidence_tree(*, source: Path, destination: Path) -> Path:
    """Copy an evidence directory tree for offline restore."""

    if not source.is_dir():
        raise FileNotFoundError(f"evidence directory not found: {source}")
    if destination.exists():
        raise FileExistsError(f"backup destination already exists: {destination}")
    shutil.copytree(source, destination)
    return destination


def timestamped_backup_dir(base: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return base / stamp


__all__ = ["backup_evidence_tree", "backup_sqlite_online", "timestamped_backup_dir"]
