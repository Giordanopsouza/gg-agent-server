---
id: 014-pubsub
feature: server
status: done
depends_on: [002-domain-types]
---

# In-process pub/sub

## Migration preflight

- **Target end-state:** a generic in-process `PubSub[Event]` with subscribe, publish, unsubscribe. Max 50 subscribers. No Redis.
- **Temporary legacy bridges:** none.
- **Forbidden legacy dependencies:** a message broker, HTTP webhooks.
- **Bridge removal task:** n/a.
- **Boundary enforcement:** one slow subscriber cannot raise in the publisher. Isolate errors per subscriber.

## Scope

Implement pub/sub used by the WebSocket layer.

## Acceptance criteria

- [x] `publish(event)` delivers to all current subscribers.
- [x] `unsubscribe` stops further deliveries.
- [x] A subscriber that raises does not block the others.
- [x] The 51st subscribe is rejected with a domain error.
- [x] Unit tests do not start FastAPI.

## Out of scope

- WebSocket framing (`015`). Webhook POSTs.

## Log

### [PA] 2026-08-21 13:45 — Grooming

OpenHands pub/sub is just asyncio fan-out. Copy that honesty. You do not need NATS to learn event streaming.

### [SWE] 2026-08-23 11:00 — Implementation

Added generic async `PubSub` fan-out in `gg.server.pubsub`. It caps unique subscribers at 50, supports explicit unsubscribe, and isolates subscriber failures while delivering concurrently to the remaining subscribers. Unit tests cover delivery, unsubscribe, failure isolation, and the cap without starting FastAPI.

### [Tester] 2026-08-23 10:30 — Verified

Task tests passed: `PYTHONPATH=packages/gg-server:packages/gg-sdk uv run pytest packages/gg-server/tests/test_pubsub.py` (4 passed). Task-specific Ruff passed. The full suite reached 87 passed; two existing session-key tests fail because their default persistent `workspace/conversations` is non-empty. Full-repository Ruff has seven existing errors outside this task (the notebook and `test_local_conversation.py`).
