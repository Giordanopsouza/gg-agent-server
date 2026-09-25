---
id: 024-real-llm-loop
feature: loop
status: pending
depends_on: [016-local-server-demo]
---

# Real LLM loop

## Scope

Replace the scripted agent with a real model behind a flag or env key. Only after slice 1 is green.

## Acceptance criteria

- [ ] With no API key, the dummy agent still runs.
- [ ] With a key, a small prompt can produce a `write_file` action and `NOTES.md`.
- [ ] Events still persist and stream on the WebSocket.

## Out of scope

- Streaming tokens as first delivery. Tool calling for ten tools. Sub-agents.

## Log

### [PA] 2026-08-21 13:45 — Grooming

Parked on purpose. A model hides whether your loop works. Do slices 1 to 3 with the dummy agent first.
