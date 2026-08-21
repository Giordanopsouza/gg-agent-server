---
id: 012-conversation-routes
feature: server
status: pending
depends_on: [011-conversation-service, 010-session-api-key]
---

# Conversation HTTP routes

## Migration preflight

- **Target end-state:** REST under `/api/conversations` for create, get, and list. Re-POST of the same id reattaches and returns 200.
- **Temporary legacy bridges:** none.
- **Forbidden legacy dependencies:** query-string session keys, agent blobs in `meta.json`.
- **Bridge removal task:** n/a.
- **Boundary enforcement:** request bodies parse into SDK types at the router. Handlers do not accept raw dicts.

## Scope

Expose create, get, and list over HTTP.

## Acceptance criteria

- [ ] `POST /api/conversations` with `{working_dir}` returns 201 and an id.
- [ ] `POST /api/conversations` with an existing `id` returns 200 and the same record.
- [ ] `GET /api/conversations/{id}` returns the record or 404.
- [ ] `GET /api/conversations` lists ids from disk.
- [ ] Auth from `010` applies to these routes.

## Out of scope

- Sending messages (`013`). Agent profile ids.

## Log

### [PA] 2026-08-21 13:45 — Grooming

Reattach is resume. Do not add `/resume`. Same trick as OpenHands.
