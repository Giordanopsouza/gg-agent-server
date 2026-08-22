---
id: 010-session-api-key
feature: server
status: done
depends_on: [009-app-health]
---

# Session API key

## Migration preflight

- **Target end-state:** empty key list leaves `/api/*` open. A non-empty list requires header `X-Session-API-Key`. `/health` stays public.
- **Temporary legacy bridges:** none.
- **Forbidden legacy dependencies:** cookies, Bearer tokens, JWT.
- **Bridge removal task:** n/a.
- **Boundary enforcement:** tests cover both open and keyed modes.

## Scope

Add the auth dependency and apply it to a placeholder `/api` router.

## Acceptance criteria

- [x] No keys configured: `GET /api/conversations` is allowed once that route exists. For now a stub `/api/_auth_check` returns 200 without a header.
- [x] Keys configured: missing or wrong header returns 401.
- [x] Correct header returns 200.
- [x] `/health` never requires the key.

## Out of scope

- Workspace cookies. OpenAI `/v1` Bearer. WebSocket first-frame auth (`015` adds that).

## Log

### [PA] 2026-08-21 13:45 — Grooming

One header. Localhost bind is the other half of safety. Do not invent a user table.

### [SWE] 2026-08-22 14:00 — Implementation

Added `check_session_api_key` in `dependencies.py`, a placeholder `api_router` with
`GET /api/_auth_check`, and wired the dependency onto the router in `create_app`.
Tests cover open mode, keyed 401/200, and public `/health`.
