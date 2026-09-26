---
id: 055-repository-task-runner
feature: modal-background-tasks
status: done
depends_on: [051-modal-sandbox-lifecycle, 054-running-agent-messages-and-cancel]
---

# Run repository tasks and record test evidence

## Scope

Add a sandbox task supervisor that prepares an allowlisted repository, runs Pi against a fixed starting revision, executes configured checks, and exposes a durable local result manifest.

## Acceptance criteria

- [x] Resolve and record the requested base ref to a commit SHA before editing; clone that revision and assign the unique task branch.
- [x] Repository configuration supplies bounded bootstrap and test commands. Submission never accepts arbitrary infrastructure configuration or secret values.
- [x] Clone credentials are process-scoped and removed from Git URLs/configuration. Pi's long-lived environment contains no bot token; secret values are never embedded in prompts.
- [x] Starting execution is a nonblocking HTTP operation: persist its task/execution identity before launching work and acknowledge promptly. Repeated requests, including a retry after the original connection drops, return the same execution identity and status without launching a second Pi process.
- [x] Reconnecting a control plane attaches to the existing execution. If the sandbox's supervisor or agent-server process itself restarts and cannot prove that execution is still owned and running, mark it failed; never reconstruct and rerun the prompt from persisted conversation data. Orphaned execution processes are stopped before cleanup is confirmed.
- [x] Pi, repository setup, tests, and finalization share a configurable task deadline, defaulting to 60 minutes from reservation; commands have bounded output and cancellation.
- [x] Record base/head revisions, changed files or bounded patch, check command, exit status, duration, output/truncation markers, and agent outcome. Not run and timeout are distinct from passed.
- [x] A no-change run produces an explicit `no_changes` result. Agent failure preserves the evidence already available and never claims successful checks.
- [x] A live Modal demo edits a controlled test repository and retrieves truthful test evidence; injected bootstrap, agent, and test failures produce distinct outcomes.
- [x] Tests interrupt the start-response connection and restart the supervisor after execution begins; neither scenario can launch a second agent execution for the same task.

## Out of scope

PR publication, dynamic framework detection, arbitrary repository environments, dependency services, and nested Docker.

## Log

### [PA] 2026-09-19 17:54 UTC — Grooming

The repository contract requires operator-configured checks rather than treating an agent's narrative as test proof. The reviewed revision defines nonblocking, idempotent execution startup and failure on lost supervisor ownership.

### [Orchestrator] 2026-09-19 18:12 UTC — Approved plan recorded

The user approved the feature plan and requested planning artifacts directly on `main`. Recorded as pending; implementation has not started.

### [SWE] 2026-09-20 — Sandbox task supervisor and evidence manifest

Added in-sandbox supervisor routes (`POST /api/task-executions/start`, execution
and manifest reads), operator repository profiles, bounded bootstrap/check
capture, git prep with resolved base SHA, idempotent execution persistence,
control-plane `TaskSupervisorClient`, Modal sandbox env forwarding, and an
opt-in repository-task demo module. Deterministic supervisor tests cover
idempotent start, restart ownership loss, and explicit `no_changes` outcomes.

### [PR Reviewer] 2026-09-20 — Merged

PR [#24](https://github.com/Giordanopsouza/gg-agent-server/pull/24) merged to
`main`. Task archived to `docs/tasks/done/`.
