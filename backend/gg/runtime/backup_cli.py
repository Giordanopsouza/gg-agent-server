"""Operator CLI for SQLite online backup and evidence trees."""

from __future__ import annotations

import argparse
from pathlib import Path

from gg.runtime.backup import (
    backup_evidence_tree,
    backup_sqlite_online,
    timestamped_backup_dir,
)
from gg.runtime.ledger import TaskLedger


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backup gg runtime control-plane state"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    backup = sub.add_parser("backup", help="Create an online SQLite backup")
    backup.add_argument("--db", required=True, help="Path to gg-tasks.sqlite")
    backup.add_argument(
        "--destination",
        required=True,
        help="Directory that will receive a timestamped backup folder",
    )
    backup.add_argument(
        "--evidence-dir",
        default=None,
        help="Optional evidence directory to copy alongside the database",
    )

    args = parser.parse_args()
    if args.command == "backup":
        destination_root = Path(args.destination)
        bundle = timestamped_backup_dir(destination_root)
        bundle.mkdir(parents=True, exist_ok=False)
        with TaskLedger(db_path=args.db) as ledger:
            backup_sqlite_online(ledger=ledger, destination=bundle / "tasks.sqlite")
        if args.evidence_dir:
            backup_evidence_tree(
                source=Path(args.evidence_dir),
                destination=bundle / "evidence",
            )
        print(bundle)


if __name__ == "__main__":
    main()
