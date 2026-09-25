---
id: 057-task-supervision-results-and-cleanup
feature: modal-background-tasks
status: done
depends_on: [052-fifo-dispatch-and-recovery, 056-idempotent-draft-pr-publication]
---

# Supervise tasks, archive results, and release sandboxes

## Scope

Complete the production task lifecycle: relay messages and events, recover supervision, archive results, cancel work, and terminate sandboxes automatically.

## Acceptance criteria

- [x] Enable production dispatch only after the actual supervisor, finalization, evidence archival, and cleanup are connected; remove task 052's temporary dispatch wiring.
- [x] Authenticated task endpoints expose cursor-based event replay/live WebSocket updates, message receipts, cancellation, results, and explicit retry.
- [x] Copy events incrementally to SQLite using source identity/sequence for deduplication. Reconnect after control-plane downtime backfills retained sandbox events before continuing live delivery.
- [x] Persist accepted outbound messages before forwarding; sandbox message IDs reconcile a lost HTTP acknowledgement. Never replay an uncertain Pi delivery automatically.
- [x] Settlement and message acceptance share a serialized boundary: before finalization, drain accepted receipts to confirmed Pi delivery or explicitly mark each undelivered receipt failed/uncertain with a reason. Never silently discard a message accepted before settlement, and never reopen a settled run by implicitly replaying it.
- [x] Nonblocking supervisor start is idempotent across control-plane restart and lost HTTP responses; resume supervision from the persisted execution identity rather than sending a new prompt.
- [x] Queue cancellation prevents allocation; running cancellation stops execution and finalizes evidence. Repeated cancellation is idempotent. A publication already in progress may leave a PR, which must be reported.
- [x] Persist the final result and evidence manifest before normal sandbox termination. If archival fails, retry within the cleanup budget; record incomplete evidence rather than falsely claiming successful archival.
- [x] Confirm provider termination before releasing the reservation. Termination failures remain visible and consume capacity while the reconciler retries.
- [x] Sandbox crashes/timeouts preserve captured evidence, identify possible missing tail data, mark failed, and do not rerun the agent.
- [x] Retry is available only after terminal execution and confirmed cleanup; it creates a linked new queued task with a fresh branch and explicitly reports any prior branch/PR. Default retry uses the recorded starting SHA; callers may select a different permitted ref.
- [ ] Integration tests exercise ordinary success, restart mid-run, replay after disconnect, completion during downtime, cancel/publication race, archive failure, sandbox loss, and cleanup failure.

## Out of scope

Resumable finished sandboxes, automatic retries of coding work, and indefinite result preservation.

## Log

### [PA] 2026-09-19 17:54 UTC — Grooming

This slice joins the independently proven components into the complete API workflow. Evidence preservation is bounded, not a promise of recovering data lost with a crashed sandbox. Reviewed message settlement and restart behavior explicitly.

### [Orchestrator] 2026-09-19 18:12 UTC — Approved plan recorded

The user approved the feature plan and requested planning artifacts directly on `main`. Recorded as pending; implementation has not started.

### [SWE] 2026-09-20 — Control-plane supervision wired

Added ledger schema v5 (supervision identity, event copies, message receipts,
archived results), `TaskSupervisionManager` (start/resume execution, event sync,
message settlement, finalization, optional publication, cleanup), authenticated
task routes (`events`, `messages`, `cancel`, `result`, `retry`, live WebSocket),
production dispatch enablement, and integration tests for no-change completion
and idempotent queued cancel.

### [PR Reviewer] 2026-09-20 — Merged

PR [#27](https://github.com/Giordanopsouza/gg-agent-server/pull/27) merged to
`main`. Full fault-matrix integration coverage remains a follow-up; core wiring
and subset integration tests shipped. Task archived to `docs/tasks/done/`.
