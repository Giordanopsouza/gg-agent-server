---
id: 007-in-process-demo
feature: loop
status: done
depends_on: [006-local-conversation-loop]
---

# In-process demo

## Scope

Add a runnable module and an integration test that prove slice 1a without a server.

## Acceptance criteria

- [x] The demo command exits 0.
- [x] `NOTES.md` exists and is non-empty.
- [x] The conversation directory contains `meta.json`, `base_state.json`, and at least one event file.
- [x] An integration test runs the same path and asserts those files.

## Out of scope

- WebSocket. Auth. Reconnect.

## Log

### [PA] 2026-08-21 13:45 — Grooming

Slice 1a checkpoint. Do not start the FastAPI tasks until you have run this yourself and opened `NOTES.md`.

### [SWE] 2026-08-22 12:45 — In-process demo landed

`gg.sdk.demo.write_notes` module, integration test, and learning notebooks for slice 1a.
