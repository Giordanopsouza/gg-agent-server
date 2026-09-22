---
status: accepted
---

# One background task shape with an optional repository

A background task is a long-running prompt, whether or not its work belongs to a GitHub repository. Keep one create request and one durable lifecycle—admission, capacity reservation, sandbox execution, evidence, terminal outcome, and cleanup—for both cases. Every request supplies a prompt and idempotency key. A repository (`owner/name`) is optional; when present, the caller must also supply a base ref. There is no task-kind field or separate repository-task pipeline.

The earlier [single-host control-plane decision](0001-modal-background-tasks.md) assumed every task was a repository edit that produced a draft pull request. That made general work depend on GitHub configuration and repository profiles even when it needed neither. A task without a repository now starts in a blank workspace and skips clone and publication. A repository task clones with `GG_GITHUB_CLONE_TOKEN` and follows the same lifecycle; successful edits with changes can produce a draft PR. There are no repository allowlist or profile admission gates. Bootstrap and check commands are not required; the check outcome is `not_run` when no check runs.

This choice keeps scheduling, recovery, evidence, and API semantics in one place. It gives up mandatory repository-specific bootstrap and verification; verification must come from the task itself or subsequent review, and operators must limit the GitHub token's repository access. This ADR replaces the repository-only task shape and profile/check defaults in ADR 0001; its single-host, SQLite, Modal, capacity, and recovery decisions remain in force.

## References

- [Issue #33: One general task](https://github.com/Giordanopsouza/gg-agent-server/issues/33)
