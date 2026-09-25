---
id: 029-pi-conversation-api
feature: pi
status: done
depends_on: [027-pi-rpc-agent, 013-event-routes-and-run]
---

# Pi conversation API

## Scope

Add a discriminated agent configuration to conversation creation and persistence, wire the server to the SDK backend factory, and expose the same option through local and remote conversation clients.

## Acceptance criteria

- [x] `StartConversationRequest` accepts `agent.kind="pi"` with `provider="openrouter"`, model, and timeout; omitted `agent` defaults to dummy.
- [x] Providers other than `openrouter` are rejected by validation in this version.
- [x] `Conversation`, `RemoteConversation`, and server-side creation forward the same nested agent configuration.
- [x] `base_state.json` persists the agent configuration but never a credential value.
- [x] Reattaching or hydrating a conversation reconstructs the same backend; legacy state without `agent` reconstructs the dummy.
- [x] User message events include `role="user"`; legacy message events without a role are still eligible as the latest user prompt.
- [x] Missing/invalid Pi configuration maps to HTTP 400 and Pi process/protocol failure maps to HTTP 502 after recording status `ERROR`.
- [x] Pi events are persisted during the run and published through the existing post-run event fan-out without adding live deltas.
- [x] Tests cover create, reattach, run, list events, serialization, old-state compatibility, error responses, and the unchanged dummy default.

## Out of scope

- API keys in requests, additional providers, token streaming, multiple turns, cancellation endpoints, or runtime API changes.

## Log

### [PA] 2026-08-25 21:53 — Grooming

Keep agent selection explicit per conversation so Docker and future ACP backends can reuse the API without changing the default offline path.

### [SWE] 2026-09-07 14:46 — Implementation started

Adding the credential-free discriminated agent configuration, SDK backend
factory, persistence and hydration path, client forwarding, HTTP error mapping,
and success/failure event fan-out coverage.

### [Tester] 2026-09-07 15:38 — PASS

The isolated full suite passes with 176 tests and two opt-in integration tests
skipped. Ruff passes repository-wide. Focused coverage proves request and state
round trips, legacy defaults, local and remote forwarding, successful Pi event
persistence/fan-out, sanitized validation, and HTTP 502 error transitions for
both protocol and process failures.

### [SWE] 2026-09-07 15:38 — Complete

Implemented and verified the Pi conversation API while preserving dummy as the
offline default and keeping credentials outside transport and persistence.

### [SWE] 2026-09-07 17:46 — Archived

Moved the completed task into `docs/tasks/done`.
