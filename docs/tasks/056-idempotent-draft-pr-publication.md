---
id: 056-idempotent-draft-pr-publication
feature: modal-background-tasks
status: pending
depends_on: [050-durable-background-task-api, 055-repository-task-runner]
---

# Publish and reconcile one draft PR per task

## Migration preflight

Inspect [ADR 0001](../adr/0001-modal-background-tasks.md), GitHub's current pull-request API, and existing demo behavior. Production publication must be deterministic application code with a durable operation journal; do not use an LLM instruction as the mechanism enforcing draft-only publication or deduplication.

## Scope

Commit and push the task's changes and create or recover its draft PR using the configured bot identity. Make publication recoverable after control-plane/network failures.

## Acceptance criteria

- [ ] Persist intended repository, task branch, base, task marker, and commit before push/create side effects; never push to the base branch or force-push.
- [ ] Supply bot credentials only to required clone/push operations and host-side GitHub API calls; logs and responses omit credential values.
- [ ] Verify remote branch SHA and reconcile an existing PR by repository/head/base/task marker, including closed PRs, before retrying an uncertain publication operation.
- [ ] Repeated finalization, lost create responses, or control-plane restart produce at most one platform-created PR per task. Ambiguous conflicting remote state fails visibly instead of blindly creating another.
- [ ] Only draft PRs are created. PR bodies include task identity and measured check outcomes; no merge or automatic ready-for-review action is available.
- [ ] Completed edits with failed tests still produce a draft PR explicitly showing failed checks, and the task outcome is failed. Agent/infrastructure failure does not initiate a new PR.
- [ ] No changes means no PR. Existing published branches/PRs are recorded on cancellation or failure and never silently deleted.
- [ ] GitHub-boundary tests cover timeout after creation, an existing closed PR, remote branch conflict, failing checks, and no changes; a controlled live repository proves draft status and bot authorship.

## Out of scope

PR review, merging, rebasing existing PRs, automatic branch cleanup, and GitHub OAuth or App installation workflows.

## Log

### [PA] 2026-09-19 17:54 UTC — Grooming

Drafted publication as deterministic application behavior. Manual retries use new identities, not repeated publication under an old task.

### [Orchestrator] 2026-09-19 18:12 UTC — Approved plan recorded

The user approved the complete plan, including its displayed failed-check publication policy, and requested planning artifacts directly on `main`. Recorded as pending; implementation has not started.
