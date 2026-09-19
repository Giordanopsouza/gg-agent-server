---
id: 060-ten-sandbox-production-acceptance
feature: modal-background-tasks
status: pending
depends_on: [058-background-task-sdk-and-cli, 059-single-host-production-operations]
---

# Prove the ten-sandbox production workflow

## Migration preflight

Inspect [ADR 0001](../adr/0001-modal-background-tasks.md), all feature tasks, and their evidence. Acceptance uses the shipped CLI/API, deployed control plane, standard Modal sandboxes, and an explicitly configured disposable GitHub repository. Do not substitute mocks for the live capacity proof.

## Scope

Add a repeatable opt-in acceptance command and operator runbook proving the release's actual capacity, recovery, messaging, publication, and cleanup promises.

## Acceptance criteria

- [ ] Submit eleven controlled tasks and prove that ten agent/job executions are simultaneously active behind deterministic barriers, rather than merely ten instantiated sandboxes or sequential conversation calls. Task eleven remains queued with no eleventh reservation or sandbox.
- [ ] Release one held task and prove FIFO admission of task eleven only after the old sandbox's termination is confirmed.
- [ ] During the run, stream activity before completion, deliver one follow-up message, reconnect a client, cancel a queued task and a running task, and restart the control plane without rerunning surviving work.
- [ ] Force one sandbox loss; observe failure, preserved available evidence, and no automatic retry. Explicit retry creates a new linked task.
- [ ] Confirm edited successful tasks yield draft PRs with measured checks; exercise failed-check and no-change policies on fixtures.
- [ ] Query provider state after completion and prove all test-owned sandboxes stopped. Failed cleanup must fail the acceptance command and list resource IDs requiring action.
- [ ] Save a sanitized evidence report including configuration/image versions, observed peak resources, task transitions, queue behavior, PR links, recovery results, and remaining resources.
- [ ] Expose the command through the root Makefile, document required quotas/credentials and resource cost, and run the repository's prescribed QA sequence.
- [ ] Report the proof as ten concurrent controlled workloads on the tested host/configuration, not a general latency or availability SLA.
- [ ] Register an explicit `modal` live-test pytest marker and exclude it from both packages' ordinary unit-test Makefile targets. Live provisioning runs only through an explicitly selected opt-in command; default test discovery, ordinary unit targets, and ordinary CI never call paid provider APIs.
- [ ] Exercise follow-up from a completed task's PR branch after its sandbox is confirmed terminated; prove the new task uses that branch's resolved revision and a separate sandbox.

## Out of scope

High-volume benchmarking, chaos platform, multi-region testing, and merging or deleting generated PRs.

## Log

### [PA] 2026-09-19 17:54 UTC — Grooming

The capacity claim requires observed live ten-plus-one behavior in addition to deterministic fault tests. Reviewed the proof to require concurrent execution and explicitly opt-in provisioning.

### [Orchestrator] 2026-09-19 18:12 UTC — Approved plan recorded

The user approved the feature plan and requested planning artifacts directly on `main`. Recorded as pending; implementation has not started.
