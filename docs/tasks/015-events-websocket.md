---
id: 015-events-websocket
feature: server
status: pending
depends_on: [013-event-routes-and-run, 014-pubsub]
---

# Events WebSocket

## Migration preflight

- **Target end-state:** `WS /sockets/events/{id}` auth via first JSON frame `{"type":"auth","session_api_key":"..."}` when keys are configured. Then it subscribes and pushes events. Inbound user JSON calls `send_message` with `run=true`.
- **Temporary legacy bridges:** none.
- **Forbidden legacy dependencies:** query-string keys as the only auth path. Cookie auth.
- **Bridge removal task:** n/a.
- **Boundary enforcement:** unknown conversation closes with 4004. Bad auth closes with 4001.

## Scope

Wire pub/sub to a WebSocket and auto-run inbound messages.

## Acceptance criteria

- [ ] After connect and auth, the client receives events produced by `POST .../run`.
- [ ] An inbound chat JSON appends a message and runs the dummy agent.
- [ ] REST send still does not auto-run.
- [ ] Tests use Starlette/httpx websocket client against `create_app`.
- [ ] Reconnect on a new socket still sees persisted events via an initial snapshot or a REST list. Document which one you picked in the task log.

## Out of scope

- Streaming delta events. Resend-since timestamps. Max subscriber close 1013 unless you already have the cap from `014`.

## Log

### [PA] 2026-08-21 13:45 — Grooming

Pick snapshot-on-subscribe or "client calls GET /events". Either is fine. Log the choice. OpenHands pushes a state snapshot then live events.
