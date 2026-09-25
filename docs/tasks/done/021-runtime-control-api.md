---
id: 021-runtime-control-api
feature: runtime
status: done
depends_on: [017-server-dockerfile]
---

# Runtime control API

## Scope

The fake provisioner. One session maps to one container.

## Acceptance criteria

- [x] `POST /start` returns 201 with `url` pointing at the mapped host port and a session key.
- [x] `GET /sessions/{id}` returns `running` after `/health` on that url succeeds.
- [x] `POST /stop` stops the container and later get returns 404 or `stopped`.
- [x] Control plane auth is a single `X-API-Key` distinct from the sandbox session key.
- [x] Tests can fake Docker with a stub if full Docker is slow, plus one optional live test marked `docker`.

## Out of scope

- Pause/resume. Resource factors. sysbox. `POST /api/init` warm-pool.

## Log

### [PA] 2026-08-21 13:45 — Grooming

This is what Cloud and the Runtime API are to the SDK: HTTP that returns a host. Keep it embarrassing small. If it grows a scheduler, you have left the learning MVP.

### [SWE] 2026-08-25 15:45 — Implementation started

Adding a standalone `gg.runtime` FastAPI process with control-plane auth, an
in-memory one-session-to-one-container registry, and an injectable Docker
launcher boundary.

### [SWE] 2026-08-25 16:00 — Implementation complete

Added the standalone `gg.runtime` process, required `X-API-Key` control-plane
authentication, generated sandbox session keys, Docker-backed lifecycle and
health checks, shutdown cleanup, environment configuration, and a CLI entry.
The runtime imports the SDK launcher but an architecture test prevents it from
importing or being embedded in `gg.server`.

### [Tester] 2026-08-25 16:02 — Verified

Focused tests and new-file Ruff checks pass. The full suite passes from a clean
temporary working directory: 130 passed and one opt-in Docker test skipped.
The marked live Docker test also passed against `gg-agent-server:dev`, proving
start, health-derived running status, stop, and container cleanup. Full-repo
Ruff retains the seven pre-existing notebook and local-conversation findings.
