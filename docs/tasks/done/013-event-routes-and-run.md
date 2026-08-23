---
id: 013-event-routes-and-run
feature: server
status: done
depends_on: [012-conversation-routes]
---

# Event routes and run

## Migration preflight

- **Target end-state:** `POST /api/conversations/{id}/events` appends a user message with `run` default false. `POST /api/conversations/{id}/run` starts the dummy loop. `GET .../events` lists persisted events.
- **Temporary legacy bridges:** none.
- **Forbidden legacy dependencies:** running on every REST send by default. Match OpenHands REST: send does not run.
- **Bridge removal task:** n/a.
- **Boundary enforcement:** a second concurrent `run` returns 409.

## Scope

HTTP for send_message, run, and event listing.

## Acceptance criteria

- [x] `POST .../events` with `{content}` appends a message event and does not start the loop.
- [x] `POST .../run` runs the dummy agent and returns when finished for the MVP. Status is `finished`. `NOTES.md` exists.
- [x] `GET .../events` returns events in seq order from disk.
- [x] `POST .../run` while already running returns 409.
- [x] Unknown conversation id returns 404.

## Out of scope

- Streaming tokens. Pause. Interrupt. Goal loops.

## Log

### [PA] 2026-08-21 13:45 — Grooming

REST send stays `run=false`. WebSocket in `015` may auto-run. Keep that difference. It is a real OpenHands footgun and worth learning on purpose.

### [SWE] 2026-08-23 10:35 — Implementation

Added `SendMessageRequest` (`run` defaults false) in the SDK. `ConversationService` send/list/run: run waits on a thread, a second in-flight run raises `ConversationAlreadyRunningError`. Routes: `POST/GET .../events`, `POST .../run`. Tests in `test_event_routes.py`. 84 pytest passed.

### [Tester] 2026-08-23 10:35 — Verified

`uv run pytest` passed (84 tests). Send stays idle, run writes NOTES.md and finishes, GET lists seq order, concurrent run 409, unknown id 404.
