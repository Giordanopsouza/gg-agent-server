---
id: 014-pubsub
feature: server
status: pending
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

- [ ] `publish(event)` delivers to all current subscribers.
- [ ] `unsubscribe` stops further deliveries.
- [ ] A subscriber that raises does not block the others.
- [ ] The 51st subscribe is rejected with a domain error.
- [ ] Unit tests do not start FastAPI.

## Out of scope

- WebSocket framing (`015`). Webhook POSTs.

## Log

### [PA] 2026-08-21 13:45 — Grooming

OpenHands pub/sub is just asyncio fan-out. Copy that honesty. You do not need NATS to learn event streaming.
