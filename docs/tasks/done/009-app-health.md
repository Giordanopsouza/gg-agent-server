---
id: 009-app-health
feature: server
status: done
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

- [x] `create_app(settings)` returns a FastAPI app.
- [x] `GET /health` is liveness. `GET /ready` is 200 after lifespan startup.
- [x] `uv run python -m gg.server --host 127.0.0.1 --port 8000` serves those routes.
- [x] Tests use httpx `ASGITransport`. They do not require a real port.

## Out of scope

- `/api/conversations` (`012`). Session key checks (`010`).

## Log

### [PA] 2026-08-21 13:45 — Grooming

Keep `/ready` honest. We are not building deferred init, so `/ready` may mean the API is usable. Do not copy OpenHands warm-pool semantics.

### [SWE] 2026-08-22 13:55 — Implementation

Added `gg/server/app.py` with `create_app(settings)`, lifespan `ready_event`, and
`/health` + `/ready` routes. Added `gg/server/__main__.py` CLI (`python -m gg.server`)
with `resolve_bind_host()` defaulting to loopback when no session keys are set.
Exported `create_app` from `gg.server`. Tests in `test_app_health.py` use httpx
`ASGITransport` with `AsyncClient`.

### [Tester] 2026-08-22 13:55 — Verified

`uv run pytest` passed (54 tests). Smoke-tested `/health` and `/ready` on live server.
