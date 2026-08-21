---
id: 006-local-conversation-loop
feature: loop
status: pending
depends_on: [003-event-log, 004-local-workspace, 005-write-file-tool]
---

# Local conversation loop

## Migration preflight

- **Target end-state:** `LocalConversation` owns status, the event log, and the dummy agent. `send_message` then `run()` walks idle to running to finished and appends events.
- **Temporary legacy bridges:** none.
- **Forbidden legacy dependencies:** FastAPI, threads as the default, an LLM client.
- **Bridge removal task:** n/a.
- **Boundary enforcement:** status transitions are a small table or match, not scattered `if` flags.

## Scope

Implement `LocalConversation.send_message`, `run`, and a dummy agent that always emits one `write_file` action for `NOTES.md`.

## Acceptance criteria

- [ ] `send_message` appends an `EventKind.message` event and stays `idle` until `run`.
- [ ] `run` sets `running`, calls the dummy agent, executes tools, appends action and observation events, then sets `finished`.
- [ ] A second `run` while `running` raises a domain error.
- [ ] After `run`, `NOTES.md` exists in `working_dir` and the event log has message, action, observation, status.
- [ ] Restarting `EventLog` in a new object still lists those events.

## Out of scope

- Pause, interrupt, max iterations, stuck detection.
- HTTP wrappers (`011` to `015`).

## Log

### [PA] 2026-08-21 13:45 — Grooming

This is OpenHands `LocalConversation` with the LLM ripped out. If this task feels like the whole project, that is the point. The server only exposes this object.
