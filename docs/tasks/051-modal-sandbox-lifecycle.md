---
id: 051-modal-sandbox-lifecycle
feature: modal-background-tasks
status: pending
depends_on: [050-durable-background-task-api]
---

# Standard Modal sandbox lifecycle

## Migration preflight

Inspect [ADR 0001](../adr/0001-modal-background-tasks.md), the current Docker image and runtime launcher, and tasks 052/055/057. Add one concrete Modal integration under `gg.runtime`; do not build a provider registry or route new work through `DockerWorkspace`. Preserve existing Docker demos.

## Scope

Build a versioned standard Modal sandbox image containing the agent server, Pi, Git, and required runtime tools. Implement asynchronous create, inspect, reconnect, authenticated connect, detach, and terminate operations.

## Acceptance criteria

- [ ] Pin the image/runtime dependencies and Pi version; expose their versions in task evidence. Use standard sandboxes, with no nested Docker or VM beta dependency.
- [ ] Persist a creation intent before the network call; submit deterministic deployment/task identity through sandbox name and tags at creation.
- [ ] Record the provider ID immediately when obtained; support reconnect by ID and discovery by deployment/task identity when the create response was lost.
- [ ] Distinguish running, confirmed stopped, and unknown/unreachable provider states; a failed health request does not prove termination.
- [ ] Agent-server access uses authenticated encrypted HTTP/WebSocket connectivity. Neither sandbox credentials nor raw provider connection credentials appear in public task responses.
- [ ] Configurable defaults set both requested and hard maximum resources using the pinned Modal SDK's supported tuple configuration: `cpu=(2, 2)`, `memory=(4096, 4096)`. Verify these semantics against that SDK version. Set a five-minute startup deadline and 70-minute absolute provider timeout; document quota requirements and pricing separately rather than describing resource requests as guaranteed cost bounds.
- [ ] A runnable live smoke test creates a sandbox, authenticates to `/health`, reconnects from a fresh client, terminates it, and confirms provider termination. Boundary tests cover ambiguous creation and termination responses.

## Out of scope

Multiple providers, warm pools, snapshots, GPUs, and custom user images.

## Log

### [PA] 2026-09-19 17:54 UTC — Grooming

Drafted the concrete provider boundary. The reviewed revision makes CPU and memory hard limits explicit; implementation must verify the pinned Modal SDK behavior.

### [Orchestrator] 2026-09-19 18:12 UTC — Approved plan recorded

The user approved the feature plan and requested planning artifacts directly on `main`. Recorded as pending; implementation has not started.
