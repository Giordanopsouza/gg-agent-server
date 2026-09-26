---
id: 026-agent-backend-boundary
feature: loop
status: done
depends_on: [006-local-conversation-loop]
---

# Agent backend boundary

## Scope

Introduce an agent backend protocol with `run(prompt, workspace, emit)`, move the current scripted behavior into `DummyAgentBackend`, and make `LocalConversation` accept an injected backend while defaulting to the dummy.

## Acceptance criteria

- [x] `LocalConversation` delegates the latest user prompt and active `LocalWorkspace` to the selected backend.
- [x] `DummyAgentBackend` emits the same action and observation events and still creates `NOTES.md` with the same contents.
- [x] An injected test backend proves that prompt, workspace, and event emission cross the new boundary.
- [x] The `write_notes` demo and all existing tests continue to pass without caller changes.
- [x] Import-boundary coverage proves that `gg.sdk` does not import `gg.server`.

## Out of scope

- Pi, new event kinds, HTTP request changes, Docker, or streaming changes.

## Log

### [PA] 2026-08-25 21:53 — Grooming

Split from the local Pi plan so the conversation loop gains an agent boundary without introducing any external process or model dependency.

### [SWE] 2026-08-27 10:59 — Implementation started

Adding the SDK-owned backend protocol, moving scripted execution behind the
dummy backend, and injecting that boundary into `LocalConversation`.

### [Tester] 2026-08-27 11:03 — PASS

The isolated full suite passes with 139 tests and one opt-in Docker test
skipped. Ruff passes across `packages` and `tests`; the backend injection,
unchanged dummy demo behavior, and strengthened SDK/server import boundary are
covered directly.

### [SWE] 2026-08-27 11:03 — Complete

Implemented and verified the injectable agent backend boundary while preserving
the dummy backend as the offline default.

### [SWE] 2026-09-07 14:40 — Archived

Moved the completed task into `docs/tasks/done` before starting slice 4b.
