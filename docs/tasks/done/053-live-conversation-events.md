---
id: 053-live-conversation-events
feature: modal-background-tasks
status: done
depends_on: []
---

# Publish conversation events while Pi runs

## Migration preflight

Inspect [ADR 0001](../adr/0001-modal-background-tasks.md), `LocalConversation`, event persistence, `ConversationService.run_and_publish`, `PubSub`, and WebSocket routes. Replace the post-run publication bridge; do not introduce server imports into SDK emitters. Retain existing event identities and persisted conversation compatibility.

## Scope

Publish persisted conversation events during execution and make event replay plus live subscription race-free.

## Acceptance criteria

- [x] A client receives tool/action or assistant events before a deliberately blocked Pi run finishes.
- [x] Every published event is persisted first and has stable conversation identity and sequence.
- [x] Reconnect accepts a sequence cursor; the client can recover events without gaps across the replay/subscription boundary and deduplicate any replayed delivery.
- [x] Running a conversation does not monopolize the WebSocket receive loop or prevent independent HTTP requests.
- [x] Slow subscribers cannot block the agent or grow memory without bound; disconnect behavior includes a recoverable cursor.
- [x] Tests exercise a run paused between emissions, a concurrent replay/subscription race, disconnect/reconnect, and two isolated conversations.
- [x] Remove the end-of-run log-diff publication implementation once the new path covers existing callers.

## Out of scope

Token-by-token rendering, task-level archival, and browser UI.

## Log

### [PA] 2026-09-19 17:54 UTC — Grooming

Current publication occurs after run completion; this task establishes actual live progress without changing the package boundary.

### [Orchestrator] 2026-09-19 18:12 UTC — Approved plan recorded

The user approved the feature plan and requested planning artifacts directly on `main`. Recorded as pending; implementation has not started.

### [SWE] 2026-09-20 18:12 UTC — Implementation complete

Added a package-neutral post-persistence listener to `LocalConversation` and
bridged it into non-blocking server publication while the agent worker runs.
WebSocket replay now subscribes before taking its persisted snapshot, filters
duplicates by sequence, accepts `after_seq`, and bounds each subscriber queue.
Overflow closes with a recoverable sequence cursor. Socket-triggered runs now
execute in the background so receiving and independent HTTP traffic stay live.

### [Tester] 2026-09-20 18:12 UTC — Non-live verification passed

Added deterministic coverage for publication before a blocked run completes,
the replay/subscription race, cursor reconnect, slow-subscriber recovery, and
two-conversation isolation. Full non-live results: 95 SDK tests and 177 server
and boundary tests passed, with one Modal test skipped and four live tests
deselected. All task-053 files pass Ruff lint and formatting. Repository-wide
format checking remains blocked by eight pre-existing SDK files outside this
task.

### [SWE] 2026-09-20 18:12 UTC — Task archived

All acceptance criteria are implemented and verified. The task is moved to the
completed tracker folder on its dedicated branch.
