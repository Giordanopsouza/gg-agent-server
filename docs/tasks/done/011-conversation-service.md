---
id: 011-conversation-service
feature: server
status: done
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

- [x] `create(working_dir)` allocates an id, writes meta, returns a record.
- [x] `get(id)` hydrates from disk if the object is not in memory.
- [x] `list()` uses meta files, including conversations created in a previous process.
- [x] Unknown id raises a domain not-found error, not a raw `KeyError` at the HTTP layer.

## Out of scope

- HTTP routes (`012`). WebSocket (`015`). Run scheduling details beyond calling `LocalConversation.run`.

## Log

### [PA] 2026-08-21 13:45 — Grooming

This is OpenHands `ConversationService` plus `EventService`, collapsed. One object per conversation is enough at this size.

### [SWE] 2026-08-22 14:20 — Implementation

Added `ConversationService` in `conversation_service.py` with create/get/list,
`LocalConversation.open()` and `ConversationNotFoundError` in the SDK for disk
hydration, and wired the service onto `app.state` during FastAPI lifespan startup
so `python -m gg.server` boots a process-wide manager before routes land in 012.
Tests in `test_conversation_service.py` and `test_lifespan_wires_conversation_service`.

### [Tester] 2026-08-22 16:10 — Verified

`uv run pytest` passed (69 tests). Conversation service create/get/list and lifespan
wiring covered by new tests.
