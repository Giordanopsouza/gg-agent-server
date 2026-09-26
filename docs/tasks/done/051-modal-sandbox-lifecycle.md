---
id: 051-modal-sandbox-lifecycle
feature: modal-background-tasks
status: done
depends_on: [050-durable-background-task-api]
---

# Standard Modal sandbox lifecycle

## Scope

Build a versioned standard Modal sandbox image containing the agent server, Pi, Git, and required runtime tools. Implement asynchronous create, inspect, reconnect, authenticated connect, detach, and terminate operations.

## Acceptance criteria

- [x] Pin the image/runtime dependencies and Pi version; expose their versions in task evidence. Use standard sandboxes, with no nested Docker or VM beta dependency.
- [x] Persist a creation intent before the network call; submit deterministic deployment/task identity through sandbox name and tags at creation.
- [x] Record the provider ID immediately when obtained; support reconnect by ID and discovery by deployment/task identity when the create response was lost.
- [x] Distinguish running, confirmed stopped, and unknown/unreachable provider states; a failed health request does not prove termination.
- [x] Agent-server access uses authenticated encrypted HTTP/WebSocket connectivity. Neither sandbox credentials nor raw provider connection credentials appear in public task responses.
- [x] Configurable defaults set both requested and hard maximum resources using the pinned Modal SDK's supported tuple configuration: `cpu=(2, 2)`, `memory=(4096, 4096)`. Verify these semantics against that SDK version. Set a five-minute startup deadline and 70-minute absolute provider timeout; document quota requirements and pricing separately rather than describing resource requests as guaranteed cost bounds.
- [x] A runnable live smoke test creates a sandbox, authenticates to `/health`, reconnects from a fresh client, terminates it, and confirms provider termination. Boundary tests cover ambiguous creation and termination responses.

## Out of scope

Multiple providers, warm pools, snapshots, GPUs, and custom user images.

## Log

### [PA] 2026-09-19 17:54 UTC — Grooming

Drafted the concrete provider boundary. The reviewed revision makes CPU and memory hard limits explicit; implementation must verify the pinned Modal SDK behavior.

### [Orchestrator] 2026-09-19 18:12 UTC — Approved plan recorded

The user approved the feature plan and requested planning artifacts directly on `main`. Recorded as pending; implementation has not started.

### [SWE] 2026-09-20 15:00 UTC — Implementation started

Implementing a concrete `gg.runtime` Modal lifecycle over the durable SQLite
ledger: versioned named image, deterministic identities, crash-reconcilable
creation, explicit provider-state classification, private authenticated
connections, and opt-in live smoke coverage. The legacy Docker runtime remains
unchanged.

### [SWE] 2026-09-20 16:20 UTC — Implementation complete

Added the pinned `modal==1.5.5` integration, versioned
`gg-agent-server:2026-09-20-v1` image build/publish command, v2 SQLite creation
intent migration, deterministic name/tags, provider-ID and tag reconciliation,
explicit running/stopped/unknown states, authenticated HTTPS/WSS connect-token
material, detach/terminate operations, and a settings factory for the next
dispatcher slice. Credentials stay in the mode-0600 private ledger and are not
part of `TaskRecord` or `SandboxSnapshot`.

Version evidence (`python -m gg.runtime.modal_image --print-versions`): Modal
1.5.5, Python 3.12.11, uv 0.11.2, Node 22.23.1, Pi 0.83.0, Git 2.39.5, and
GitHub CLI 2.100.0. Quota, tuple semantics, timeouts, pricing, build, and smoke
instructions are documented in `docs/modal-sandboxes.md`.

### [Tester] 2026-09-20 16:25 UTC — PASS

Focused lifecycle/config/ledger/image suite passed (33 tests), followed by the
repository non-live suites (94 SDK tests and 151 server/boundary tests; the live
Modal smoke skipped without `GG_RUN_MODAL_TESTS=1`). The final concrete-adapter
argument test also passed in the 12-test lifecycle suite. Repository lint and
both package builds passed. Changed task files pass Ruff formatting; the
repository-wide format check remains blocked by nine pre-existing SDK formatting
differences outside task 051.

### [SWE] 2026-09-20 16:30 UTC — Task archived

Implementation commit `bb8d0ed` recorded on the task branch. All acceptance
criteria are complete; moved the tracker entry to `docs/tasks/done/`.
