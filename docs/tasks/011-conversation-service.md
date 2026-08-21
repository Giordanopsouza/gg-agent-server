---
id: 011-conversation-service
feature: server
status: pending
depends_on: [006-local-conversation-loop, 009-app-health]
---

# Conversation service

## Migration preflight

- **Target end-state:** `ConversationService` is process-wide. It creates, loads, and holds `LocalConversation` objects keyed by id. Catalog comes from `conversations_dir/*/meta.json`.
- **Temporary legacy bridges:** none.
- **Forbidden legacy dependencies:** leases, idle eviction, thread pool tuning beyond one `asyncio` task per run.
- **Bridge removal task:** n/a.
- **Boundary enforcement:** the service lives in `gg.server` and imports `gg.sdk`. The SDK still does not import the server.

## Scope

Wrap `LocalConversation` in a process manager with create, get, and list.

## Acceptance criteria

- [ ] `create(working_dir)` allocates an id, writes meta, returns a record.
- [ ] `get(id)` hydrates from disk if the object is not in memory.
- [ ] `list()` uses meta files, including conversations created in a previous process.
- [ ] Unknown id raises a domain not-found error, not a raw `KeyError` at the HTTP layer.

## Out of scope

- HTTP routes (`012`). WebSocket (`015`). Run scheduling details beyond calling `LocalConversation.run`.

## Log

### [PA] 2026-08-21 13:45 — Grooming

This is OpenHands `ConversationService` plus `EventService`, collapsed. One object per conversation is enough at this size.
