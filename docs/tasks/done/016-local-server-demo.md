---
id: 016-local-server-demo
feature: server
status: done
depends_on: [015-events-websocket, 007-in-process-demo]
---

# Local server demo

## Migration preflight

- **Target end-state:** a documented script starts the server, creates a conversation, sends a message, POSTs run, disconnects, reconnects, and finds `NOTES.md` plus the event log.
- **Temporary legacy bridges:** none.
- **Forbidden legacy dependencies:** Docker. A real LLM.
- **Bridge removal task:** n/a.
- **Boundary enforcement:** the demo talks HTTP and WebSocket only. It does not import `LocalConversation`.

## Scope

Prove slice 1b end to end, including background-agent reconnect.

## Acceptance criteria

- [x] `uv run python -m gg.sdk.demo.local_server_notes` exits 0 against a server on `127.0.0.1:8000`.
- [x] After the client process exits and a second client starts, `GET .../events` still returns the history.
- [x] `NOTES.md` is on the server working_dir.
- [x] An integration test starts `create_app` in-process and asserts reconnect.

## Out of scope

- Docker launcher (`019`). Runtime API (`021`).

## Log

### [PA] 2026-08-21 13:45 — Grooming

Slice 1 checkpoint. This is already a background agent: the server keeps the conversation after the client dies. Cloud is not what makes it background.

### [SWE] 2026-08-25 11:15 — Started

HTTP/WebSocket demo in `gg.sdk.demo.local_server_notes`. No `LocalConversation` import. Integration test will drive `create_app` in-process.

### [SWE] 2026-08-25 11:22 — Demo landed

`gg.sdk.demo.local_server_notes` creates a conversation, sends a message, POSTs run, drops the WebSocket, reconnects for the snapshot, then GETs `/events`. Integration test drives the same `run_demo` through `TestClient(create_app(...))`.

### [Tester] 2026-08-25 11:22 — Verified

`PYTHONPATH=packages/gg-server:packages/gg-sdk uv run pytest packages/gg-server/tests/test_local_server_demo.py` passed. Full suite 96 passed; two existing session-key tests still fail on the user-owned `workspace/conversations` catalog. Live smoke: server on `127.0.0.1:8000`, demo exited 0, wrote `NOTES.md`, and a second HTTP client still saw 5 events.
