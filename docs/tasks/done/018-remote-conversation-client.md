---
id: 018-remote-conversation-client
feature: docker
status: done
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

- [x] `Conversation.__new__` chooses remote when workspace has a `host`.
- [x] Create payload sends `LocalWorkspace(working_dir=...)` JSON to the server, not the remote host field.
- [x] `send_message` uses REST `run=false`. `run()` POSTs `/run`.
- [x] Integration test against `create_app` ASGI or a test server writes `NOTES.md` through the client.
- [x] `gg.sdk` still does not import `gg.server`.

## Out of scope

- `docker run` (`019`). File upload HTTP. Remote `execute_command` cwd quirks unless you need them for the demo.

## Log

### [PA] 2026-08-21 13:45 — Grooming

The factory is the product API. User code should look the same for local and remote. Convert RemoteWorkspace to a LocalWorkspace payload. That is the OpenHands trick.

### [SWE] 2026-08-25 12:59 — Implementation started

Implementing the SDK-only remote boundary: workspace connection settings, the conversation factory, synchronous REST operations, and optional WebSocket event subscription. Integration coverage will use the real FastAPI application through its test client without importing server code from `gg.sdk`.

### [SWE] 2026-08-25 13:03 — Implementation complete

Added `RemoteWorkspace`, `RemoteConversation`, the public `Conversation` factory, and a context-managed WebSocket event iterator. REST create payloads contain only the server-local `working_dir` (plus an optional conversation id); send explicitly uses `run=false`; run and event history use their dedicated routes. Session keys are applied to every REST call and the WebSocket auth frame.

### [Tester] 2026-08-25 13:03 — Verified

Task-scoped tests and the SDK import-boundary suite pass (19 tests), including an authenticated integration against `create_app` that writes `NOTES.md`. Task-scoped Ruff and `git diff --check` pass. The full suite reached 103 passing tests before the final subscription-only test was added; its two failures are the pre-existing stateful session-key assertions against the user-owned non-empty `workspace/conversations` catalog. Full-repository Ruff still reports the seven pre-existing notebook and `test_local_conversation.py` violations recorded by earlier tasks.

### [Tester] 2026-08-25 13:03 — Clean-directory full suite

Running the complete suite from a clean temporary working directory isolates the default persistence paths from the user-owned catalog: all 106 tests pass. This confirms the two repository-working-directory failures are fixture contamination rather than task 018 regressions.

### [SWE] 2026-08-25 13:08 — Completed

Acceptance criteria are verified and the task is ready to commit on its dedicated branch.
