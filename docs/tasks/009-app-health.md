---
id: 009-app-health
feature: server
status: pending
depends_on: [008-server-config]
---

# App factory and health

## Migration preflight

- **Target end-state:** `python -m gg.server` starts uvicorn. `GET /health` and `GET /ready` return 200. Default bind is `127.0.0.1`.
- **Temporary legacy bridges:** none.
- **Forbidden legacy dependencies:** conversation routes, VSCode, a global app constructed at import for tests. Tests call `create_app(settings)`.
- **Bridge removal task:** n/a.
- **Boundary enforcement:** `__main__` binds `127.0.0.1` when no session keys are configured.

## Scope

Stand up FastAPI: `create_app`, lifespan, `/health`, `/ready`, CLI entry.

## Acceptance criteria

- [ ] `create_app(settings)` returns a FastAPI app.
- [ ] `GET /health` is liveness. `GET /ready` is 200 after lifespan startup.
- [ ] `uv run python -m gg.server --host 127.0.0.1 --port 8000` serves those routes.
- [ ] Tests use httpx `ASGITransport`. They do not require a real port.

## Out of scope

- `/api/conversations` (`012`). Session key checks (`010`).

## Log

### [PA] 2026-08-21 13:45 — Grooming

Keep `/ready` honest. We are not building deferred init, so `/ready` may mean the API is usable. Do not copy OpenHands warm-pool semantics.
