"""Human-readable and JSON output helpers for the task CLI."""

from __future__ import annotations

import json
import sys
from typing import Any

from gg.sdk.domain import MessageReceipt
from gg.sdk.task_supervision import TaskEventCopy, TaskResultRecord
from gg.sdk.tasks import TaskRecord, TaskState


EXIT_OK = 0
EXIT_COMMAND_FAILED = 1
EXIT_TASK_UNSUCCESSFUL = 2

TERMINAL_STATES = {
    TaskState.COMPLETED,
    TaskState.FAILED,
    TaskState.CANCELLED,
}


def wait_exit_code(state: TaskState) -> int:
    """Exit code after ``--wait`` reaches a terminal task state."""
    if state is TaskState.COMPLETED:
        return EXIT_OK
    return EXIT_TASK_UNSUCCESSFUL


def emit_json(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, default=str) + "\n")


def emit_error(message: str, *, as_json: bool) -> None:
    if as_json:
        emit_json({"ok": False, "error": message})
    else:
        sys.stderr.write(f"error: {message}\n")


def format_task_record(record: TaskRecord) -> str:
    parts = [
        f"id={record.id}",
        f"state={record.state}",
        f"repository={record.repository}",
        f"seq={record.seq}",
    ]
    if record.base_ref is not None:
        parts.append(f"base_ref={record.base_ref}")
    if record.base_sha is not None:
        parts.append(f"base_sha={record.base_sha}")
    if record.retry_of is not None:
        parts.append(f"retry_of={record.retry_of}")
    return " ".join(parts)


def format_result(result: TaskResultRecord) -> str:
    lines = [
        f"task_id={result.task_id} state={result.state}",
        f"evidence_complete={result.evidence_complete}",
    ]
    if result.evidence_detail:
        lines.append(f"evidence_detail={result.evidence_detail}")
    if result.outcome_detail:
        lines.append(f"outcome_detail={result.outcome_detail}")
    if result.check_status:
        lines.append(f"check_status={result.check_status}")
    if result.sandbox_cleanup_status:
        lines.append(f"sandbox_cleanup_status={result.sandbox_cleanup_status}")
    if result.retry_of:
        lines.append(f"retry_of={result.retry_of}")
    if result.prior_task_branch:
        lines.append(f"prior_task_branch={result.prior_task_branch}")
    if result.prior_pr_url:
        lines.append(f"prior_pr_url={result.prior_pr_url}")
    manifest = result.manifest
    if manifest is not None:
        lines.append(
            f"agent_outcome={manifest.agent_outcome} "
            f"check_outcome={manifest.check_outcome}"
        )
        if manifest.check is not None:
            lines.append(f"check_exit_code={manifest.check.exit_code}")
    publication = result.publication
    if publication is not None and publication.pr_url:
        lines.append(f"pr_url={publication.pr_url}")
    return "\n".join(lines)


def format_message_receipt(receipt: MessageReceipt) -> str:
    detail = f" detail={receipt.detail}" if receipt.detail else ""
    return f"id={receipt.id} status={receipt.status}{detail}"


def format_event_copy(copy: TaskEventCopy) -> str:
    event = copy.event
    return (
        f"cursor={copy.cursor} seq={event.seq} kind={event.kind} "
        f"payload={json.dumps(event.payload, default=str)}"
    )
