---
id: 008-server-config
feature: server
status: pending
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

- [ ] `GG_HOST`, `GG_PORT`, `GG_CONVERSATIONS_DIR`, `GG_WORKSPACE_DIR`, `GG_SESSION_API_KEYS` parse into settings.
- [ ] Missing optional keys means `session_api_keys` is empty.
- [ ] Invalid port fails at load with a message that names the variable.
- [ ] `get_settings()` is the only public accessor.

## Out of scope

- Binding the socket (`009`). Auth middleware (`010`).

## Log

### [PA] 2026-08-21 13:45 — Grooming

Parse at the boundary. The rest of the server trusts Settings.
