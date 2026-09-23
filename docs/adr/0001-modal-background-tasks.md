---
status: accepted
---

# A single-host control plane for Modal background tasks

> The repository-only task shape, allowlist/profile gates, and mandatory check defaults below are superseded by [ADR 0002](0002-general-background-tasks.md). The requirement to preserve historical Docker demos is superseded by [ADR 0003](0003-remove-legacy-learning-surfaces.md).

Evolve the learning server into a minimal internal platform for repository-and-prompt tasks that produce draft GitHub pull requests. Use one always-on control-plane process with SQLite on a local persistent disk, standard Modal sandboxes for execution, and the existing Pi agent server inside each sandbox. Start with a CLI over an authenticated HTTP/WebSocket API and a hard maximum of ten reserved sandbox slots.

SQLite owns the durable queue, task lifecycle, capacity reservations, message receipts, event copies, and publication journal. Existing sandbox conversation persistence remains JSON files. This supersedes the original plan's JSON-only control-plane constraint and exclusions of recovery and managed infrastructure. It preserves historical Docker demos and both import boundaries: `gg.sdk` never imports `gg.server`, and `gg.runtime` reaches `gg.server` only through HTTP/WebSocket contracts.

Reserve capacity before provisioning and retain it until provider absence is confirmed. Reconcile creation identities and surviving sandboxes on restart rather than rerunning work. Graceful control-plane shutdown detaches; completed tasks archive bounded results and terminate automatically. Sandbox loss fails a task, and retry creates a new linked task with a distinct branch. A control-plane restart reattaches to surviving execution; a supervisor or agent-server restart that loses execution ownership fails that task instead of reconstructing and rerunning its prompt.

A configured GitHub bot serves allowlisted internal repositories. Application code prepares repositories, measures configured checks, and creates draft PRs; it reconciles uncertain GitHub operations before retrying. Bot credentials stay out of Pi's long-lived environment, but repositories and operators remain trusted: this release does not claim protection against malicious code extracting secrets temporarily accessible inside its execution environment.

## Trade-offs

A single host and SQLite avoid a separate database, queue broker, and distributed scheduler, at the cost of no high availability and dependence on local-disk backup/recovery. Standard Modal sandboxes avoid operating a compute fleet; nested Docker, full VMs, multiple providers, warm pools, and external-customer tenancy are excluded. Durable intent and reconciliation handle recoverable ambiguity; they do not promise exactly-once execution across arbitrary failures.

## Product defaults

Tasks use configured repository bootstrap and test commands. Edits with failing checks still produce a clearly labelled draft PR and a failed task outcome; no changes produce a completed result with no PR. Agent or infrastructure failure does not initiate publication. Published branches and PRs remain available after cancellation or failure. Live messaging uses Pi steering at safe boundaries; acceptance does not mean the agent has acted. Manual retry starts from the predecessor's recorded base SHA unless a different permitted ref is supplied. A new follow-up task may start from a previous PR branch after its original sandbox terminates.

| Setting | Default |
|---|---|
| Active capacity | Ten reservations, including unresolved creation and cleanup |
| Pending queue | 100 tasks |
| Sandbox resources | 2 CPU and 4 GiB memory, with hard limits |
| Startup deadline | Five minutes |
| Task deadline | 60 minutes from capacity reservation |
| Provider lifetime limit | 70 minutes |
| Terminal-result retention | Seven days |
| Per-task evidence | 10 MiB logs/events and 25 MiB artifacts |
| Total evidence | 5 GiB |
| Minimum free disk for admission | 1 GiB |
| Compact deduplication records | 90 days |

Limits are configurable; the capacity limit may be lowered but not raised above ten for this release. Retention, truncation, and incomplete evidence are visible to callers. Active or unresolved sandbox ownership records are never evicted.

## Approval and delivery

Accepted by the user on 2026-09-19. The user requested the approved planning artifacts directly on `main`; this does not authorize implementation directly on `main` or change the repository's one-task/one-branch/one-PR workflow. Tasks [050](../tasks/050-durable-background-task-api.md) through [060](../tasks/060-ten-sandbox-production-acceptance.md) define delivery. Terms are defined in the [glossary](../glossary.md).

## References

- [Modal Sandboxes](https://modal.com/docs/guide/sandboxes)
- [Modal sandbox networking and security](https://modal.com/docs/guide/sandbox-networking)
- [GitHub pull-request API](https://docs.github.com/en/rest/pulls/pulls)
- [SQLite online backup](https://www.sqlite.org/backup.html)
