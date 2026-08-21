---
id: 013-event-routes-and-run
feature: server
status: pending
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

- [ ] `POST .../events` with `{content}` appends a message event and does not start the loop.
- [ ] `POST .../run` runs the dummy agent and returns when finished for the MVP. Status is `finished`. `NOTES.md` exists.
- [ ] `GET .../events` returns events in seq order from disk.
- [ ] `POST .../run` while already running returns 409.
- [ ] Unknown conversation id returns 404.

## Out of scope

- Streaming tokens. Pause. Interrupt. Goal loops.

## Log

### [PA] 2026-08-21 13:45 — Grooming

REST send stays `run=false`. WebSocket in `015` may auto-run. Keep that difference. It is a real OpenHands footgun and worth learning on purpose.
