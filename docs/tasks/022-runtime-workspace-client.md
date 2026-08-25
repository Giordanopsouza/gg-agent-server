---
id: 022-runtime-workspace-client
feature: runtime
status: done
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

- [x] Constructor takes `runtime_api_url` and `runtime_api_key`.
- [x] After enter, `host` is the sandbox url from `/start`.
- [x] `Conversation(..., workspace=ws)` uses `RemoteConversation`.
- [x] Exit stops the session.
- [x] Unit tests stub httpx. They do not require Docker.

## Out of scope

- The live demo (`023`). Cloud-style sandbox spec ids.

## Log

### [PA] 2026-08-21 13:45 — Grooming

Two HTTP planes, like OpenHands `APIRemoteWorkspace`. Control plane then agent-server plane. If you collapse them into one client that shells docker, you skipped the lesson.

### [SWE] 2026-08-25 17:25 — Implementation started

Adding an SDK-side `RuntimeWorkspace` that provisions through the runtime HTTP
control plane, then delegates conversations to the existing remote agent-server
transport. Lifecycle tests will stub both HTTP planes without Docker.

### [SWE] 2026-08-25 17:29 — Implementation complete

Added the public `RuntimeWorkspace` SDK launcher with separate control-plane and
sandbox credentials, context-managed `/start` and `/stop` calls, optional
`keep_alive`, and delegation to the existing `RemoteConversation` transport.

### [Tester] 2026-08-25 17:29 — Verified

The focused launcher and import-boundary suite passes with 19 tests. The full
suite passes from a clean temporary working directory with 133 passed and one
opt-in Docker test skipped. Task files pass Ruff lint and format checks. Full-repo
Ruff retains the seven pre-existing notebook and local-conversation findings.
