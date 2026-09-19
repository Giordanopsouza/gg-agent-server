---
id: 054-running-agent-messages-and-cancel
feature: modal-background-tasks
status: pending
depends_on: [053-live-conversation-events]
---

# Message and cancel a running Pi agent

## Migration preflight

Inspect [ADR 0001](../adr/0001-modal-background-tasks.md), the pinned Pi RPC documentation, `AgentBackend`, `PiRpcAgent`, `LocalConversation`, and conversation routes. Replace the one-shot-only control restriction with the smallest Pi-compatible control surface. Keep any compatibility bridge confined to existing callers and remove it when all callers migrate in this task.

## Scope

Add idempotent messages for a running conversation and cooperative cancellation. Persist message acceptance and delivery outcomes without promising exactly-once effects across a subprocess failure.

## Acceptance criteria

- [ ] A message with a client-generated ID is durably accepted once; duplicate requests return the existing receipt and conflicting reuse is rejected.
- [ ] Pi receives steering messages at its supported safe boundary, in accepted order. API documentation distinguishes accepted, delivered-to-Pi, and failed/unknown delivery from acted upon.
- [ ] Verify steer, abort, acknowledgement, and settlement against the image's pinned Pi version, not an unrelated installed version.
- [ ] A lost acknowledgement leaves delivery uncertain and is not automatically replayed into Pi. Report it to the caller.
- [ ] Atomically stop accepting messages when finalization begins; race tests prove each request is either accepted for the running phase or explicitly rejected.
- [ ] Cancellation aborts Pi, then terminates its process tree after a configurable grace period; it cannot leave an agent writing after cancellation is confirmed.
- [ ] HTTP/WebSocket integration tests send a message and cancel while a fake RPC process remains active; a live Pi smoke test proves steering reaches the running process.

## Out of scope

Resuming completed environments, changing agent/model mid-task, and exactly-once LLM behavior.

## Log

### [PA] 2026-09-19 17:54 UTC — Grooming

Steering is a real backend change, not merely an additional endpoint. Delivery ambiguity is explicit.

### [Orchestrator] 2026-09-19 18:12 UTC — Approved plan recorded

The user approved the feature plan and requested planning artifacts directly on `main`. Recorded as pending; implementation has not started.
