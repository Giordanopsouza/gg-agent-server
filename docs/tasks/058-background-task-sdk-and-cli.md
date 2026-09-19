---
id: 058-background-task-sdk-and-cli
feature: modal-background-tasks
status: pending
depends_on: [057-task-supervision-results-and-cleanup]
---

# SDK and CLI for background coding tasks

## Migration preflight

Inspect [ADR 0001](../adr/0001-modal-background-tasks.md), SDK conventions, and the `cli-tool-python` spec. Add a client over public HTTP/WebSocket contracts; prohibit imports from `gg.server` or `gg.runtime` and avoid exposing provider credentials.

## Scope

Ship an SDK task client and a Click command-line entry point for the full task workflow.

## Acceptance criteria

- [ ] Declare the user-facing entry point in gg-sdk's `pyproject.toml`. Commands cover `submit`, `list`, `show`, `follow`, `message`, `cancel`, `result`, and `retry`.
- [ ] Submit accepts repository, prompt or prompt file, optional base ref, and an idempotency key. The CLI generates and exposes the key before a request so an uncertain submission can be safely repeated; keep structured output valid.
- [ ] Follow shows live activity and reconnects using the latest durable cursor without duplicating displayed events; Ctrl-C stops following without cancelling the task.
- [ ] Messages show receipt status; completed/finalizing tasks explain why messaging is unavailable. Explicit cancel is required to stop a task.
- [ ] Result and retry clearly show test outcome, PR URL when present, incomplete evidence, cleanup state, and prior task linkage.
- [ ] Credentials come from typed settings, never required command-line arguments; HTTPS is the default and insecure HTTP is restricted to explicit loopback development.
- [ ] All commands offer useful `--help` and structured JSON output; exit codes distinguish command failure from a successfully retrieved failed task, with `--wait` behavior documented.
- [ ] SDK integration tests and CLI smoke tests exercise the complete workflow against a real local HTTP service with controlled provider boundaries.
- [ ] Demonstrate a follow-up after automatic sandbox termination: submit a new prompt with the previous PR's branch as the permitted base ref, resolve its current SHA, and create a fresh task/environment/branch. The original completed task remains unchanged.

## Out of scope

Web UI, terminal UI framework, and direct Modal SDK access from the client.

## Log

### [PA] 2026-09-19 17:54 UTC — Grooming

CLI is the first client; the same authenticated API remains available to a future frontend. The reviewed revision proves new follow-up work after the original sandbox terminates.

### [Orchestrator] 2026-09-19 18:12 UTC — Approved plan recorded

The user approved the feature plan and requested planning artifacts directly on `main`. Recorded as pending; implementation has not started.
