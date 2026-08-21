---
id: 024-real-llm-loop
feature: loop
status: pending
depends_on: [016-local-server-demo]
---

# Real LLM loop

## Migration preflight

- **Target end-state:** `LocalConversation` can call an LLM instead of the dummy agent, still emitting action and observation events.
- **Temporary legacy bridges:** none.
- **Forbidden legacy dependencies:** baking a vendor SDK into `gg.server`. Keep the model client in `gg.sdk`.
- **Bridge removal task:** n/a.
- **Boundary enforcement:** dummy agent remains the default so tests stay offline.

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
