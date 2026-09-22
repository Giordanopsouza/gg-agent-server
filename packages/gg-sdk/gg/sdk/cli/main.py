"""Click entry point for background task operations."""

from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path

import click

from gg.sdk.cli import output as out
from gg.sdk.task_client import TaskClient, TaskClientError, TaskNotFoundError
from gg.sdk.task_settings import load_task_client_settings
from gg.sdk.task_supervision import RetryTaskRequest, TaskEventCopy, TaskMessageRequest
from gg.sdk.tasks import CreateTaskRequest, TaskRecord, TaskState


def _open_client() -> TaskClient:
    return TaskClient(load_task_client_settings())


@click.group()
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Emit structured JSON on stdout.",
)
@click.pass_context
def main(ctx: click.Context, as_json: bool) -> None:
    """Submit and supervise background tasks."""
    ctx.ensure_object(dict)
    ctx.obj["as_json"] = as_json


@main.command("submit")
@click.option(
    "--repository", default=None, help="Optional GitHub owner/name repository."
)
@click.option("--prompt", default=None, help="Task prompt text.")
@click.option(
    "--prompt-file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Read the prompt from a file.",
)
@click.option("--base-ref", default=None, help="Required with --repository.")
@click.option(
    "--idempotency-key",
    default=None,
    help="Reuse to safely retry an uncertain submission.",
)
@click.option(
    "--wait",
    is_flag=True,
    help=(
        "Block until the task reaches a terminal state. "
        "Exit 0 when completed, 2 when failed or cancelled."
    ),
)
@click.pass_context
def submit_cmd(
    ctx: click.Context,
    repository: str | None,
    prompt: str | None,
    prompt_file: Path | None,
    base_ref: str | None,
    idempotency_key: str | None,
    wait: bool,
) -> None:
    """Submit a new background task."""
    as_json: bool = ctx.obj["as_json"]
    prompt_text = _read_prompt(prompt, prompt_file)
    key = idempotency_key or str(uuid.uuid4())
    if not as_json:
        sys.stderr.write(f"idempotency_key: {key}\n")
    request = CreateTaskRequest(
        repository=repository,
        prompt=prompt_text,
        idempotency_key=key,
        base_ref=base_ref,
    )
    try:
        with _open_client() as client:
            response = client.submit(request)
            record = response.record
            if wait:
                record = _wait_for_terminal(client, record.id)
    except (TaskClientError, ValueError) as exc:
        _fail(as_json, str(exc))
        raise SystemExit(out.EXIT_COMMAND_FAILED) from exc

    _emit_submit(as_json, key, response.created, record)
    if wait:
        raise SystemExit(out.wait_exit_code(record.state))


@main.command("list")
@click.pass_context
def list_cmd(ctx: click.Context) -> None:
    """List tasks in FIFO order."""
    as_json: bool = ctx.obj["as_json"]
    try:
        with _open_client() as client:
            records = client.list_tasks()
    except (TaskClientError, ValueError) as exc:
        _fail(as_json, str(exc))
        raise SystemExit(out.EXIT_COMMAND_FAILED) from exc

    if as_json:
        out.emit_json(
            {
                "ok": True,
                "tasks": [item.model_dump(mode="json") for item in records],
            }
        )
    else:
        for record in records:
            sys.stdout.write(out.format_task_record(record) + "\n")


@main.command("show")
@click.argument("task_id")
@click.option(
    "--wait",
    is_flag=True,
    help="Block until the task reaches a terminal state.",
)
@click.pass_context
def show_cmd(ctx: click.Context, task_id: str, wait: bool) -> None:
    """Show one task record."""
    as_json: bool = ctx.obj["as_json"]
    try:
        with _open_client() as client:
            record = client.get_task(task_id)
            if wait:
                record = _wait_for_terminal(client, task_id)
    except TaskNotFoundError as exc:
        _fail(as_json, str(exc))
        raise SystemExit(out.EXIT_COMMAND_FAILED) from exc
    except (TaskClientError, ValueError) as exc:
        _fail(as_json, str(exc))
        raise SystemExit(out.EXIT_COMMAND_FAILED) from exc

    if as_json:
        out.emit_json({"ok": True, "task": record.model_dump(mode="json")})
    else:
        sys.stdout.write(out.format_task_record(record) + "\n")
    if wait:
        raise SystemExit(out.wait_exit_code(record.state))


@main.command("follow")
@click.argument("task_id")
@click.option(
    "--after",
    type=int,
    default=0,
    show_default=True,
    help="Durable event cursor to start after.",
)
@click.pass_context
def follow_cmd(ctx: click.Context, task_id: str, after: int) -> None:
    """Stream live task activity; Ctrl-C stops without cancelling the task."""
    as_json: bool = ctx.obj["as_json"]
    displayed = after
    try:
        with _open_client() as client:
            while True:
                displayed = _emit_backlog(client, task_id, displayed, as_json=as_json)
                try:
                    with client.subscribe_events(
                        task_id, after=displayed
                    ) as subscription:
                        while True:
                            try:
                                copy = subscription.receive(timeout=1.0)
                            except TimeoutError:
                                continue
                            displayed = _emit_copy(copy, displayed, as_json=as_json)
                except KeyboardInterrupt:
                    break
                except OSError:
                    continue
    except (TaskNotFoundError, TaskClientError, ValueError) as exc:
        _fail(as_json, str(exc))
        raise SystemExit(out.EXIT_COMMAND_FAILED) from exc


@main.command("message")
@click.argument("task_id")
@click.argument("content")
@click.option(
    "--message-id",
    default=None,
    help="Idempotent message id; generated when omitted.",
)
@click.pass_context
def message_cmd(
    ctx: click.Context,
    task_id: str,
    content: str,
    message_id: str | None,
) -> None:
    """Send a steering message to a running task."""
    as_json: bool = ctx.obj["as_json"]
    msg_id = message_id or str(uuid.uuid4())
    request = TaskMessageRequest(id=msg_id, content=content)
    try:
        with _open_client() as client:
            record = client.get_task(task_id)
            if record.state in {
                TaskState.COMPLETED,
                TaskState.FAILED,
                TaskState.CANCELLED,
                TaskState.FINALIZING,
            }:
                detail = (
                    f"task {task_id} is {record.state} and is not accepting messages; "
                    "use cancel only while a task is queued or running"
                )
                _fail(as_json, detail)
                raise SystemExit(out.EXIT_COMMAND_FAILED)
            receipt = client.send_message(task_id, request)
    except TaskNotFoundError as exc:
        _fail(as_json, str(exc))
        raise SystemExit(out.EXIT_COMMAND_FAILED) from exc
    except TaskClientError as exc:
        _fail(as_json, exc.detail)
        raise SystemExit(out.EXIT_COMMAND_FAILED) from exc
    except ValueError as exc:
        _fail(as_json, str(exc))
        raise SystemExit(out.EXIT_COMMAND_FAILED) from exc

    if as_json:
        out.emit_json(
            {
                "ok": True,
                "message_id": msg_id,
                "receipt": receipt.model_dump(mode="json"),
            }
        )
    else:
        sys.stdout.write(out.format_message_receipt(receipt) + "\n")


@main.command("cancel")
@click.argument("task_id")
@click.pass_context
def cancel_cmd(ctx: click.Context, task_id: str) -> None:
    """Explicitly cancel a queued or running task."""
    as_json: bool = ctx.obj["as_json"]
    try:
        with _open_client() as client:
            record = client.cancel(task_id)
    except (TaskNotFoundError, TaskClientError, ValueError) as exc:
        detail = exc.detail if isinstance(exc, TaskClientError) else str(exc)
        _fail(as_json, detail)
        raise SystemExit(out.EXIT_COMMAND_FAILED) from exc

    if as_json:
        out.emit_json({"ok": True, "task": record.model_dump(mode="json")})
    else:
        sys.stdout.write(out.format_task_record(record) + "\n")


@main.command("result")
@click.argument("task_id")
@click.option(
    "--wait",
    is_flag=True,
    help=(
        "Block until the task reaches a terminal state before fetching the result. "
        "Exit 0 when completed, 2 when failed or cancelled."
    ),
)
@click.pass_context
def result_cmd(ctx: click.Context, task_id: str, wait: bool) -> None:
    """Show archived outcome, evidence, and publication references."""
    as_json: bool = ctx.obj["as_json"]
    try:
        with _open_client() as client:
            if wait:
                record = _wait_for_terminal(client, task_id)
            else:
                record = client.get_task(task_id)
            result = client.result(task_id)
    except TaskNotFoundError as exc:
        _fail(as_json, str(exc))
        raise SystemExit(out.EXIT_COMMAND_FAILED) from exc
    except (TaskClientError, ValueError) as exc:
        _fail(as_json, str(exc))
        raise SystemExit(out.EXIT_COMMAND_FAILED) from exc

    if as_json:
        out.emit_json({"ok": True, "result": result.model_dump(mode="json")})
    else:
        sys.stdout.write(out.format_result(result) + "\n")
    if wait:
        raise SystemExit(out.wait_exit_code(record.state))


@main.command("retry")
@click.argument("task_id")
@click.option(
    "--idempotency-key",
    required=True,
    help="Idempotency key for the replacement task.",
)
@click.option("--base-ref", default=None, help="Override the predecessor base ref.")
@click.pass_context
def retry_cmd(
    ctx: click.Context,
    task_id: str,
    idempotency_key: str,
    base_ref: str | None,
) -> None:
    """Start a linked replacement task after confirmed cleanup."""
    as_json: bool = ctx.obj["as_json"]
    request = RetryTaskRequest(idempotency_key=idempotency_key, base_ref=base_ref)
    try:
        with _open_client() as client:
            predecessor = client.get_task(task_id)
            predecessor_result = client.result(task_id)
            response = client.retry(task_id, request)
    except (TaskNotFoundError, TaskClientError, ValueError) as exc:
        detail = exc.detail if isinstance(exc, TaskClientError) else str(exc)
        _fail(as_json, detail)
        raise SystemExit(out.EXIT_COMMAND_FAILED) from exc

    if as_json:
        out.emit_json(
            {
                "ok": True,
                "created": response.created,
                "predecessor_state": predecessor.state,
                "predecessor_result": predecessor_result.model_dump(mode="json"),
                "task": response.record.model_dump(mode="json"),
            }
        )
    else:
        sys.stdout.write(
            f"predecessor={predecessor.id} state={predecessor.state}\n"
            f"{out.format_task_record(response.record)}\n"
        )
        if predecessor_result.prior_pr_url:
            sys.stdout.write(f"prior_pr_url={predecessor_result.prior_pr_url}\n")
        if predecessor_result.prior_task_branch:
            sys.stdout.write(
                f"prior_task_branch={predecessor_result.prior_task_branch}\n"
            )


def _read_prompt(prompt: str | None, prompt_file: Path | None) -> str:
    if prompt_file is not None and prompt is not None:
        raise click.UsageError("use either --prompt or --prompt-file, not both")
    if prompt_file is not None:
        text = prompt_file.read_text(encoding="utf-8")
    elif prompt is not None:
        text = prompt
    else:
        raise click.UsageError("one of --prompt or --prompt-file is required")
    if not text.strip():
        raise click.UsageError("prompt must be non-empty")
    return text


def _wait_for_terminal(client: TaskClient, task_id: str) -> TaskRecord:
    while True:
        record = client.get_task(task_id)
        if record.state in out.TERMINAL_STATES:
            return record
        time.sleep(0.25)


def _emit_submit(
    as_json: bool, idempotency_key: str, created: bool, record: TaskRecord
) -> None:
    if as_json:
        out.emit_json(
            {
                "ok": True,
                "idempotency_key": idempotency_key,
                "created": created,
                "task": record.model_dump(mode="json"),
            }
        )
    else:
        sys.stdout.write(out.format_task_record(record) + "\n")


def _fail(as_json: bool, message: str) -> None:
    out.emit_error(message, as_json=as_json)


def _emit_backlog(
    client: TaskClient,
    task_id: str,
    displayed: int,
    *,
    as_json: bool,
) -> int:
    for copy in client.list_events(task_id, after=displayed):
        displayed = _emit_copy(copy, displayed, as_json=as_json)
    return displayed


def _emit_copy(copy: TaskEventCopy, displayed: int, *, as_json: bool) -> int:
    if copy.cursor <= displayed:
        return displayed
    if as_json:
        out.emit_json({"ok": True, "event": copy.model_dump(mode="json")})
    else:
        sys.stdout.write(out.format_event_copy(copy) + "\n")
    return max(displayed, copy.cursor)


if __name__ == "__main__":
    main()
