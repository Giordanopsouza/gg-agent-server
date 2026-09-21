---
id: 059-single-host-production-operations
feature: modal-background-tasks
status: done
depends_on: [057-task-supervision-results-and-cleanup]
---

# Operate the single-host control plane

## Migration preflight

Inspect [ADR 0001](../adr/0001-modal-background-tasks.md), root guidance, existing Makefiles, and deployment configuration. Update current project guidance to distinguish production SQLite task state from JSON conversation files and historical learning constraints. Do not change the one-task/one-branch/one-PR workflow.

## Scope

Provide a reproducible always-on deployment, bounded storage and resource policies, and tested backup/recovery procedures for one persistent-disk host.

## Acceptance criteria

- [x] Provide a documented service installation with one worker, local persistent filesystem, restart policy, restricted data permissions, graceful shutdown, and TLS reverse-proxy configuration.
- [x] Protect every task/event/message/result endpoint using configured internal API keys. Keep secrets out of URLs, logs, saved task models, and image layers; include rotation instructions.
- [x] Readiness reports database availability, scheduler ownership, and unresolved capacity without confusing a provider outage with confirmed sandbox loss.
- [x] Default bounds are seven-day terminal-result retention, 10 MiB event/log evidence and 25 MiB artifacts per task, 5 GiB total evidence, and 1 GiB minimum free disk. Limits are configurable and truncation/expiry are explicit.
- [x] Storage pressure stops admission before unsafe writes; active/unresolved ownership records are never evicted. Expiring task payloads retains compact idempotency and remote-side-effect tombstones for 90 days.
- [x] Demonstrate a supported SQLite online backup plus evidence backup, and restore with dispatch disabled until provider reconciliation completes. Do not copy a live WAL database as if a single file were a consistent backup.
- [x] Document bot fine-grained permissions, repository allowlists/check commands, Modal quota/setup, resource and deadline settings with their cost implications, leaked-resource recovery, and the trusted-internal-repository threat model.
- [x] Update `AGENTS.md` and current planning guidance with the approved storage/recovery direction, retaining historical tasks and user edits.
- [x] Run deployment smoke checks for authenticated health/task access, second-process rejection, restart recovery, storage pressure, retention, and backup restore.

## Out of scope

High availability, network-mounted SQLite, managed database, billing, external-customer isolation, and a full monitoring stack.

## Log

### [PA] 2026-09-19 17:54 UTC — Grooming

This task supersedes obsolete production guidance without rewriting historical decisions or repository workflow. Deployment and retention defaults were made explicit for approval.

### [Orchestrator] 2026-09-19 18:12 UTC — Approved plan recorded

The user approved the feature plan and requested planning artifacts directly on `main`. Recorded as pending; implementation has not started.

### [SWE] 2026-09-21 11:05 UTC — Implementation

Added runtime storage/retention/backup/readiness surfaces, ledger schema v6 tombstones,
operator docs under `docs/single-host-production.md`, deploy templates, and
`production-smoke-tests`. Full unit suite and smoke checks pass.
