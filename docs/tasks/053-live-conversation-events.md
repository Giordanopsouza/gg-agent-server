---
id: 053-live-conversation-events
feature: modal-background-tasks
status: pending
depends_on: []
---

# Publish conversation events while Pi runs

## Migration preflight

Inspect [ADR 0001](../adr/0001-modal-background-tasks.md), `LocalConversation`, event persistence, `ConversationService.run_and_publish`, `PubSub`, and WebSocket routes. Replace the post-run publication bridge; do not introduce server imports into SDK emitters. Retain existing event identities and persisted conversation compatibility.

## Scope

Publish persisted conversation events during execution and make event replay plus live subscription race-free.

## Acceptance criteria

- [ ] A client receives tool/action or assistant events before a deliberately blocked Pi run finishes.
- [ ] Every published event is persisted first and has stable conversation identity and sequence.
- [ ] Reconnect accepts a sequence cursor; the client can recover events without gaps across the replay/subscription boundary and deduplicate any replayed delivery.
- [ ] Running a conversation does not monopolize the WebSocket receive loop or prevent independent HTTP requests.
- [ ] Slow subscribers cannot block the agent or grow memory without bound; disconnect behavior includes a recoverable cursor.
- [ ] Tests exercise a run paused between emissions, a concurrent replay/subscription race, disconnect/reconnect, and two isolated conversations.
- [ ] Remove the end-of-run log-diff publication implementation once the new path covers existing callers.

## Out of scope

Token-by-token rendering, task-level archival, and browser UI.

## Log

### [PA] 2026-09-19 17:54 UTC — Grooming

Current publication occurs after run completion; this task establishes actual live progress without changing the package boundary.

### [Orchestrator] 2026-09-19 18:12 UTC — Approved plan recorded

The user approved the feature plan and requested planning artifacts directly on `main`. Recorded as pending; implementation has not started.
