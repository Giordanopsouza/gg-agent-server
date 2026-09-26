---
id: 058-background-task-sdk-and-cli
feature: modal-background-tasks
status: done
depends_on: [057-task-supervision-results-and-cleanup]
---

# SDK and CLI for background coding tasks

## Scope

Ship an SDK task client and a Click command-line entry point for the full task workflow.

## Acceptance criteria

- [x] Declare the user-facing entry point in gg-sdk's `pyproject.toml`. Commands cover `submit`, `list`, `show`, `follow`, `message`, `cancel`, `result`, and `retry`.
- [x] Submit accepts repository, prompt or prompt file, optional base ref, and an idempotency key. The CLI generates and exposes the key before a request so an uncertain submission can be safely repeated; keep structured output valid.
- [x] Follow shows live activity and reconnects using the latest durable cursor without duplicating displayed events; Ctrl-C stops following without cancelling the task.
- [x] Messages show receipt status; completed/finalizing tasks explain why messaging is unavailable. Explicit cancel is required to stop a task.
- [x] Result and retry clearly show test outcome, PR URL when present, incomplete evidence, cleanup state, and prior task linkage.
- [x] Credentials come from typed settings, never required command-line arguments; HTTPS is the default and insecure HTTP is restricted to explicit loopback development.
- [x] All commands offer useful `--help` and structured JSON output; exit codes distinguish command failure from a successfully retrieved failed task, with `--wait` behavior documented.
- [x] SDK integration tests and CLI smoke tests exercise the complete workflow against a real local HTTP service with controlled provider boundaries.
- [x] Demonstrate a follow-up after automatic sandbox termination: submit a new prompt with the previous PR's branch as the permitted base ref, resolve its current SHA, and create a fresh task/environment/branch. The original completed task remains unchanged.

## Out of scope

Web UI, terminal UI framework, and direct Modal SDK access from the client.

## Log

### [PA] 2026-09-19 17:54 UTC — Grooming

CLI is the first client; the same authenticated API remains available to a future frontend. The reviewed revision proves new follow-up work after the original sandbox terminates.

### [Orchestrator] 2026-09-19 18:12 UTC — Approved plan recorded

The user approved the feature plan and requested planning artifacts directly on `main`. Recorded as pending; implementation has not started.

### [SWE] 2026-09-20 21:10 UTC — Implementation complete

Shipped `TaskClient`, `TaskClientSettings`, and the `gg-task` Click CLI (`submit`, `list`, `show`, `follow`, `message`, `cancel`, `result`, `retry`) over authenticated runtime HTTP/WebSocket routes. Added unit, CLI smoke, and ASGI integration tests including follow-up submission from a prior task branch.
