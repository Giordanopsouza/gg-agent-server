---
id: 027-pi-rpc-agent
feature: pi
status: done
depends_on: [026-agent-backend-boundary]
---

# Pi RPC agent

## Migration preflight

- **Target end-state:** `PiRpcAgent` runs one headless Pi subprocess per conversation run and translates its final RPC events into the gg event log.
- **Temporary legacy bridges:** none; the dummy backend remains the default when Pi is not explicitly selected.
- **Forbidden legacy dependencies:** no TypeScript SDK embedding, ACP adapter, vendor client in `gg.server`, persisted API key, or network-dependent default test.
- **Bridge removal task:** n/a.
- **Boundary enforcement:** subprocess management, settings, parsing, and event translation live in `gg.sdk` and are exercised with a fake executable.

## Scope

Add `PiAgentSettings` and a synchronous `PiRpcAgent` backend that speaks strict JSONL over stdio, uses OpenRouter with Gemini 3.7 Flash, and cleans up the subprocess after a single run.

## Acceptance criteria

- [x] `PiAgentSettings` fixes `provider="openrouter"`, defaults `model` to `google/gemini-3.7-flash`, and defaults `timeout_seconds` to 600.
- [x] The subprocess command is `pi --mode rpc --no-session --no-approve --provider openrouter --model <model>` with `cwd=workspace.working_dir`.
- [x] Startup fails clearly when `pi` or `OPENROUTER_API_KEY` is unavailable, without exposing the key.
- [x] The prompt command uses a correlation id and a failed prompt response becomes a typed agent error.
- [x] Strict LF-delimited JSON parsing accepts optional trailing CR and rejects malformed messages.
- [x] `message_end`, `tool_execution_start`, and `tool_execution_end` map to final message, action, and observation events; delta/update events are ignored.
- [x] `agent_settled` is the only successful terminal event and adds the final status.
- [x] `EventKind.ERROR` and the `RUNNING -> ERROR` transition persist sanitized process, protocol, and timeout failures.
- [x] Timeout sends `abort`, waits up to five seconds, then terminates and kills if required.
- [x] Stderr is drained concurrently with bounded capture so a noisy child cannot deadlock or exhaust memory.
- [x] Offline tests cover success, missing binary, missing key, rejected prompt, malformed JSON, early exit, timeout, and cleanup.

## Out of scope

- HTTP API integration, live token/tool-progress streaming, Pi session persistence, multiple providers, images, or Docker.

## Log

### [PA] 2026-08-25 21:53 — Grooming

Use Pi's official RPC subprocess mode directly from Python; ACP is intentionally deferred until the local product path is proven.

### [SWE] 2026-08-27 14:41 — Implementation started

Implementing the SDK-owned Pi RPC backend, typed failure boundary, persisted
conversation error transition, and an offline fake-process test matrix.

### [Tester] 2026-08-27 15:03 — PASS

The isolated full suite passes with 153 tests and one opt-in Docker test
skipped. Ruff passes across `packages` and `tests`; the fake Pi executable
covers command construction, strict framing, event translation, typed and
sanitized failures, timeout abort, bounded stderr draining, and forced cleanup.

### [SWE] 2026-08-27 15:03 — Complete

Implemented and verified the synchronous Pi RPC backend and conversation error
boundary without adding a server dependency or a network-dependent default test.
