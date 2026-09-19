---
id: 055-repository-task-runner
feature: modal-background-tasks
status: pending
depends_on: [051-modal-sandbox-lifecycle, 054-running-agent-messages-and-cancel]
---

# Run repository tasks and record test evidence

## Migration preflight

Inspect [ADR 0001](../adr/0001-modal-background-tasks.md), the existing GitHub Docker demo, and tasks 052/056/057. Reuse Pi and conversation contracts, not the demo's prompt-controlled clone/publish flow. Production repository setup and test-result collection must be application code.

## Scope

Add a sandbox task supervisor that prepares an allowlisted repository, runs Pi against a fixed starting revision, executes configured checks, and exposes a durable local result manifest.

## Acceptance criteria

- [ ] Resolve and record the requested base ref to a commit SHA before editing; clone that revision and assign the unique task branch.
- [ ] Repository configuration supplies bounded bootstrap and test commands. Submission never accepts arbitrary infrastructure configuration or secret values.
- [ ] Clone credentials are process-scoped and removed from Git URLs/configuration. Pi's long-lived environment contains no bot token; secret values are never embedded in prompts.
- [ ] Starting execution is a nonblocking HTTP operation: persist its task/execution identity before launching work and acknowledge promptly. Repeated requests, including a retry after the original connection drops, return the same execution identity and status without launching a second Pi process.
- [ ] Reconnecting a control plane attaches to the existing execution. If the sandbox's supervisor or agent-server process itself restarts and cannot prove that execution is still owned and running, mark it failed; never reconstruct and rerun the prompt from persisted conversation data. Orphaned execution processes are stopped before cleanup is confirmed.
- [ ] Pi, repository setup, tests, and finalization share a configurable task deadline, defaulting to 60 minutes from reservation; commands have bounded output and cancellation.
- [ ] Record base/head revisions, changed files or bounded patch, check command, exit status, duration, output/truncation markers, and agent outcome. Not run and timeout are distinct from passed.
- [ ] A no-change run produces an explicit `no_changes` result. Agent failure preserves the evidence already available and never claims successful checks.
- [ ] A live Modal demo edits a controlled test repository and retrieves truthful test evidence; injected bootstrap, agent, and test failures produce distinct outcomes.
- [ ] Tests interrupt the start-response connection and restart the supervisor after execution begins; neither scenario can launch a second agent execution for the same task.

## Out of scope

PR publication, dynamic framework detection, arbitrary repository environments, dependency services, and nested Docker.

## Log

### [PA] 2026-09-19 17:54 UTC — Grooming

The repository contract requires operator-configured checks rather than treating an agent's narrative as test proof. The reviewed revision defines nonblocking, idempotent execution startup and failure on lost supervisor ownership.

### [Orchestrator] 2026-09-19 18:12 UTC — Approved plan recorded

The user approved the feature plan and requested planning artifacts directly on `main`. Recorded as pending; implementation has not started.
