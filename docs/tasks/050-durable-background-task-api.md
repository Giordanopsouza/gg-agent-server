---
id: 050-durable-background-task-api
feature: modal-background-tasks
status: pending
depends_on: []
---

# Durable background task API

## Migration preflight

Inspect [ADR 0001](../adr/0001-modal-background-tasks.md), the runtime API, and tasks 051–060. New production task state must use SQLite; existing Docker session APIs remain a separate learning/demo surface, never an implementation dependency. Preserve existing JSON conversation files. Enforce both package boundaries: `gg.sdk` never imports `gg.server`, and `gg.runtime` never imports `gg.server`; host orchestration reaches the agent server through HTTP/WebSocket contracts.

## Scope

Add shared frozen task models in `gg.sdk` and a SQLite task ledger behind authenticated submission, list, and detail routes in `gg.runtime`. Accept an allowlisted GitHub repository, prompt, and optional base ref.

## Acceptance criteria

- [ ] `POST /tasks` validates the configured repository allowlist, bounded prompt, and base-ref syntax, then durably returns a task ID and queued status without provisioning.
- [ ] Submission requires an idempotency key: identical requests return the original task; reuse with different input returns a conflict.
- [ ] Persist a FIFO sequence, timestamps, request identity, unique branch `codex/task-<task-id>`, nullable resolved base SHA, and optional `retry_of`.
- [ ] Define task states `queued`, `starting`, `running`, `finalizing`, `completed`, `failed`, and `cancelled`. Store outcome details, check status, and sandbox cleanup status separately.
- [ ] SQLite schema versioning and transactions survive process termination without exposing partially submitted tasks; an unsupported future schema fails startup explicitly.
- [ ] A configured pending-queue bound defaults to 100; overflow receives a retryable capacity response without creating a task.
- [ ] API integration tests prove restart persistence, concurrent duplicate submissions, FIFO ordering, allowlist rejection, and SDK import independence.

## Out of scope

Dispatch, Modal calls, user accounts, per-user quotas, and replacing conversation JSON persistence.

## Log

### [PA] 2026-09-19 17:54 UTC — Grooming

Drafted durable admission as the first independently testable production surface. The reviewed revision also preserves the runtime/server import boundary.

### [Orchestrator] 2026-09-19 18:12 UTC — Approved plan recorded

The user approved the feature plan, local task files, ADR, and glossary, then requested these artifacts directly on `main`. Recorded as pending; implementation has not started.
