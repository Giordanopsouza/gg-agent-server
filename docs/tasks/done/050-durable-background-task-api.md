---
id: 050-durable-background-task-api
feature: modal-background-tasks
status: done
depends_on: []
---

# Durable background task API

## Scope

Add shared frozen task models in `gg.sdk` and a SQLite task ledger behind authenticated submission, list, and detail routes in `gg.runtime`. Accept an allowlisted GitHub repository, prompt, and optional base ref.

## Acceptance criteria

- [x] `POST /tasks` validates the configured repository allowlist, bounded prompt, and base-ref syntax, then durably returns a task ID and queued status without provisioning.
- [x] Submission requires an idempotency key: identical requests return the original task; reuse with different input returns a conflict.
- [x] Persist a FIFO sequence, timestamps, request identity, nullable resolved base SHA, and optional `retry_of`.
- [x] Define task states `queued`, `starting`, `running`, `finalizing`, `completed`, `failed`, and `cancelled`. Store outcome details, check status, and sandbox cleanup status separately.
- [x] SQLite schema versioning and transactions survive process termination without exposing partially submitted tasks; an unsupported future schema fails startup explicitly.
- [x] API integration tests prove restart persistence, concurrent duplicate submissions, FIFO ordering, allowlist rejection, and SDK import independence.

## Out of scope

Dispatch, Modal calls, user accounts, per-user quotas, and replacing conversation JSON persistence.

## Log

### [PA] 2026-09-19 17:54 UTC — Grooming

Drafted durable admission as the first independently testable production surface. The reviewed revision also preserves the runtime/server import boundary.

### [Orchestrator] 2026-09-19 18:12 UTC — Approved plan recorded

The user approved the feature plan, local task files, ADR, and glossary, then requested these artifacts directly on `main`. Recorded as pending; implementation has not started.

### [SWE] 2026-09-19 22:41 UTC — Implementation started

Adding frozen task models to `gg.sdk` and a SQLite task ledger with authenticated `POST /tasks`, `GET /tasks`, and `GET /tasks/{id}` routes in `gg.runtime`. Ledger owns schema versioning, FIFO sequence, idempotency, and transactional submission.

### [SWE] 2026-09-19 22:46 UTC — Implementation complete

Surface shipped:

- `packages/gg-sdk/gg/sdk/tasks.py` — frozen `CreateTaskRequest`, `TaskRecord`, `TaskState` (seven lifecycle states) with separate `outcome_detail`, `check_status`, and `sandbox_cleanup_status` fields. Exported from `gg.sdk`.
- `packages/gg-server/gg/runtime/ledger.py` — `TaskLedger`: SQLite with `schema_meta` versioning, WAL, `BEGIN IMMEDIATE` transactions, monotonic FIFO `seq`, unique `idempotency_key`, and restart-safe persistence. Unsupported future schema raises at startup.
- `packages/gg-server/gg/runtime/task_service.py` — `TaskService`: allowlist, prompt, base-ref, and idempotency-key validation plus conflict detection on reuse with different input.
- `packages/gg-server/gg/runtime/task_routes.py` — authenticated `POST /tasks` (201 created / 200 idempotent replay / 409 conflict / 422 validation), `GET /tasks` (FIFO), `GET /tasks/{id}` (404).
- `packages/gg-server/gg/runtime/config.py` — `task_db_path`, `repository_allowlist`, `max_prompt_chars`, `max_base_ref_chars`, `max_idempotency_key_chars` settings and env loaders.
- `create_app` opens/closes the ledger in the lifespan and mounts the router behind the existing `X-API-Key` dependency.

Tests: `test_tasks.py`, `test_task_ledger.py` (FIFO, idempotent replay, restart persistence, sequence continuation, unsupported future schema, concurrent duplicate submissions), `test_task_api.py` (created/queued, idempotent 200, conflict 409, allowlist rejection, base-ref validation, FIFO list, get/404, auth, restart persistence), plus `test_runtime_config.py` additions. Full non-live suite: 226 passed. Boundary tests (`gg.sdk` and `gg.runtime` never import `gg.server`) remain green.

Out of scope per task: dispatch, Modal, retry execution, and capacity reservation land in 051/052.

### [PR Reviewer] 2026-09-20 12:51 UTC — Merged

PR [#20](https://github.com/Giordanopsouza/gg-agent-server/pull/20) merged to `main` (merge commit `25e28f4`). All acceptance criteria checked; 226 non-live tests green; boundary tests green. Task archived to `docs/tasks/done/`.
