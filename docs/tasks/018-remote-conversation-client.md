---
id: 018-remote-conversation-client
feature: docker
status: pending
depends_on: [012-conversation-routes, 013-event-routes-and-run, 015-events-websocket]
---

# Remote conversation client

## Migration preflight

- **Target end-state:** `RemoteConversation` is an HTTP and WebSocket client. `Conversation(workspace=RemoteWorkspace(host=...))` returns it. The server still builds `LocalConversation`.
- **Temporary legacy bridges:** none.
- **Forbidden legacy dependencies:** importing `gg.server` from the client. Sharing memory with the server process.
- **Bridge removal task:** n/a.
- **Boundary enforcement:** factory tests use a fake host and do not call Docker.

## Scope

Implement `RemoteWorkspace` as a host plus api_key, and `RemoteConversation` for create, send, run, list events, and optional WS subscribe.

## Acceptance criteria

- [ ] `Conversation.__new__` chooses remote when workspace has a `host`.
- [ ] Create payload sends `LocalWorkspace(working_dir=...)` JSON to the server, not the remote host field.
- [ ] `send_message` uses REST `run=false`. `run()` POSTs `/run`.
- [ ] Integration test against `create_app` ASGI or a test server writes `NOTES.md` through the client.
- [ ] `gg.sdk` still does not import `gg.server`.

## Out of scope

- `docker run` (`019`). File upload HTTP. Remote `execute_command` cwd quirks unless you need them for the demo.

## Log

### [PA] 2026-08-21 13:45 — Grooming

The factory is the product API. User code should look the same for local and remote. Convert RemoteWorkspace to a LocalWorkspace payload. That is the OpenHands trick.
