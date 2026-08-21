---
id: 022-runtime-workspace-client
feature: runtime
status: pending
depends_on: [018-remote-conversation-client, 021-runtime-control-api]
---

# Runtime workspace client

## Migration preflight

- **Target end-state:** `RuntimeWorkspace` calls `POST {runtime_api_url}/start` with `X-API-Key`, then becomes `RemoteWorkspace` against the returned url and sandbox session key.
- **Temporary legacy bridges:** none.
- **Forbidden legacy dependencies:** kubectl. Talking to Docker from this class. Docker stays in the runtime API process.
- **Bridge removal task:** n/a.
- **Boundary enforcement:** closing the workspace calls `POST /stop` unless `keep_alive=True`.

## Scope

Client launcher that only speaks HTTP to the fake runtime, then HTTP to the sandbox.

## Acceptance criteria

- [ ] Constructor takes `runtime_api_url` and `runtime_api_key`.
- [ ] After enter, `host` is the sandbox url from `/start`.
- [ ] `Conversation(..., workspace=ws)` uses `RemoteConversation`.
- [ ] Exit stops the session.
- [ ] Unit tests stub httpx. They do not require Docker.

## Out of scope

- The live demo (`023`). Cloud-style sandbox spec ids.

## Log

### [PA] 2026-08-21 13:45 — Grooming

Two HTTP planes, like OpenHands `APIRemoteWorkspace`. Control plane then agent-server plane. If you collapse them into one client that shells docker, you skipped the lesson.
