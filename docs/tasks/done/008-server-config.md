---
id: 008-server-config
feature: server
status: done
depends_on: [001-repo-scaffolding]
---

# Server config

## Migration preflight

- **Target end-state:** `gg.server` loads a frozen settings object from env. No other module reads `os.environ`.
- **Temporary legacy bridges:** none.
- **Forbidden legacy dependencies:** OpenHands `OH_*` names copied blindly. Use `GG_*`.
- **Bridge removal task:** n/a.
- **Boundary enforcement:** a test greps `gg/server` for `os.environ` / `os.getenv` outside the config module.

## Scope

Typed config for host, port, conversations dir, workspace dir, and optional session API keys.

## Acceptance criteria

- [x] `GG_HOST`, `GG_PORT`, `GG_CONVERSATIONS_DIR`, `GG_WORKSPACE_DIR`, `GG_SESSION_API_KEYS` parse into settings.
- [x] Missing optional keys means `session_api_keys` is empty.
- [x] Invalid port fails at load with a message that names the variable.
- [x] `get_settings()` is the only public accessor.

## Out of scope

- Binding the socket (`009`). Auth middleware (`010`).

## Log

### [PA] 2026-08-21 13:45 — Grooming

Parse at the boundary. The rest of the server trusts Settings.

### [SWE] 2026-08-22 12:47 — Implementation

`gg/server/config.py` holds a frozen `Settings` pydantic model and a cached
`get_settings()` singleton. `_load_settings()` is the only place that reads
`os.getenv`; it parses `GG_HOST`, `GG_PORT`, `GG_CONVERSATIONS_DIR`,
`GG_WORKSPACE_DIR`, and `GG_SESSION_API_KEYS` (comma-separated). Invalid port
raises `ValueError` naming `GG_PORT`. `reset_settings()` is a test-only cache
clear. Exported `Settings` and `get_settings` from `gg.server.__init__`.

Boundary enforced by `tests/test_server_config_boundary.py`, which AST-scans
every `gg/server/*.py` except `config.py` for `os.environ`/`os.getenv` (and
`from os import environ/getenv`) and fails on any hit. Parsing tests live in
`packages/gg-server/tests/test_config.py`.

### [Tester] 2026-08-22 13:24 — Verified

`uv run pytest` passed (45 tests). Merged in PR #5.
