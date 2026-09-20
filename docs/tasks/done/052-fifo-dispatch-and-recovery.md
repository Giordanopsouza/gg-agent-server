---
id: 052-fifo-dispatch-and-recovery
feature: modal-background-tasks
status: done
depends_on: [050-durable-background-task-api, 051-modal-sandbox-lifecycle]
---

# FIFO dispatch and restart recovery

## Migration preflight

Inspect [ADR 0001](../adr/0001-modal-background-tasks.md) and tasks 051/055/057. Production dispatch must use the durable ledger rather than `RuntimeService._sessions`. Existing stop-everything-on-close behavior remains confined to the legacy Docker runtime. Enforce that separation through lifecycle integration tests.

## Scope

Run one lifespan-managed scheduler that transactionally reserves capacity and provisions FIFO queued work. Recover existing reservations and surviving Modal sandboxes before admitting additional work.

Production dispatch remains explicitly disabled until task 057 connects the complete task supervisor and finalization path. This task ships a separately invoked lifecycle demonstration with cleanup of all demo-owned resources.

## Acceptance criteria

- [x] An exclusive local process lock prevents a second control-plane instance or worker from opening the same production deployment for dispatch.
- [x] At most ten reservations exist across starting, running, finalizing, termination-pending, and unresolved creation states. Configuration may lower the limit, never raise it above ten for this release.
- [x] FIFO admission uses durable submission order; concurrent wakeups cannot claim the same task or slot twice.
- [x] Startup reconciles ledger reservations against provider IDs and deployment tags before dispatch. Adopt the unique matching sandbox; conflicting matches or unknown state block affected capacity and expose an operator-visible condition.
- [x] Never repeat an ambiguous create blindly. Confirm absence or reconcile the existing identity before another create attempt.
- [x] SIGTERM stops admission and detaches from surviving sandboxes; restart reconnects without rerunning the prompt or allocating a replacement.
- [x] Confirmed sandbox loss marks its task failed, retains captured evidence, and never automatically retries agent execution.
- [x] Deterministic fault tests cover crashes before creation, after provider creation but before ID persistence, during running work, and during termination.
- [x] Startup refuses to enable production dispatch without the completed runner/finalization wiring; queued requests remain durable and visibly pending while dispatch is disabled.
- [x] A standalone lifecycle demo exercises reservation, provisioning, reconnect, and termination without accepting production coding work. Its finally/reconciliation path cleans owned sandboxes and reports unresolved resources as failure.
- [x] Task 057 is the explicit activation/removal point: remove temporary demo-only dispatch wiring and enable production dispatch only when the actual supervisor, evidence archival, and cleanup path are connected.
- [x] Existing runtime-boundary tests remain green: `gg.runtime` communicates with `gg.server` through its public HTTP/WebSocket contracts and never imports server implementation modules.

## Out of scope

Multiple hosts, distributed leases, high availability, automatic task retry, and priority scheduling.

## Log

### [PA] 2026-09-19 17:54 UTC — Grooming

Separated task outcome from resource ownership so uncertain or failed cleanup cannot silently free capacity. The reviewed revision keeps production dispatch disabled until task 057.

### [Orchestrator] 2026-09-19 18:12 UTC — Approved plan recorded

The user approved the feature plan and requested planning artifacts directly on `main`. Recorded as pending; implementation has not started.

### [SWE] 2026-09-20 14:31 UTC — Implementation complete

Added schema-v3 durable capacity reservations, transactional FIFO claiming, a
hard configurable ceiling of ten, an exclusive deployment lock, startup
reconciliation, provider-condition reporting, confirmed-loss failure handling,
and graceful detach semantics. Production admission remains rejected until task
057; `GET /tasks/dispatch/status` reports durable pending work and recovery
conditions. Added a standalone Modal lifecycle demo with mandatory cleanup.

### [Tester] 2026-09-20 14:31 UTC — Non-live verification passed

Deterministic scheduler fault coverage passes for crashes before create, after
provider create but before ID persistence, during running work, and during
termination. Concurrent reservation, migration, capacity, shutdown-boundary,
dispatch-gate, and operator-status tests pass. Full non-live results: 172
server/boundary tests and 94 SDK tests passed; the gg-server distribution built
successfully. The opt-in live Modal demo was not invoked without external Modal
credentials. Repository-wide Ruff formatting remains blocked by 15 pre-existing
files outside task 052; all task-052 files pass Ruff lint and formatting.

### [SWE] 2026-09-20 14:34 UTC — Task archived

All acceptance criteria are implemented and verified. The task is being
committed on its dedicated branch and moved to the completed tracker folder.
