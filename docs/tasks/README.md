# Tasks

File-based task tracker (`TRACKER_MODE: file`). **One markdown file per
atomic task**, committed to the repo. Root task files are the active plan.

Plan overview: [overview.md](overview.md). Architecture:
[About the OpenHands agent-server](../architecture.md).

## Current plan

Slices 1 to 3. Slice 1a is the in-process loop. Slice 1b is that loop
behind HTTP. Do not skip 1a.

| Slice | Feature slug | Tasks | Stop when |
|---|---|---|---|
| 1a | `scaffold`, `loop` | [001](done/001-repo-scaffolding.md) … [007](done/007-in-process-demo.md) | `NOTES.md` from a Python module, no server |
| 1b | `server` | [008](done/008-server-config.md) … [016](done/016-local-server-demo.md) | Reconnect to a local server and still see events |
| 2 | `docker` | [017](017-server-dockerfile.md) … [020](020-docker-sandbox-demo.md) | `NOTES.md` inside a container |
| 3 | `runtime` | [021](021-runtime-control-api.md) … [023](023-runtime-api-demo.md) | Same demo through `POST /start` |
| later | `loop` | [backlog/024](backlog/024-real-llm-loop.md) | Real LLM, after 016 |

## Folders

- `tasks/*.md` — current plan only (plus this README and `overview.md`).
- `tasks/backlog/*.md` — valid work intentionally outside the current
  plan; move a file back to root when it is prioritized.
- `tasks/done/*.md` — completed historical work.

The frontmatter `status:` remains authoritative after a move.

## Format

`tasks/<NNN>-<slug>.md` (or the same filename under `backlog/` /
`done/`), where `NNN` is a zero-padded monotonic counter:

```
tasks/
├── done/
│   ├── 001-repo-scaffolding.md    # status: done
│   ├── 002-domain-types.md        # status: done
│   ├── 003-event-log.md           # status: done
│   ├── 004-local-workspace.md     # status: done
│   ├── 005-write-file-tool.md     # status: done
│   ├── 006-local-conversation-loop.md # status: done
│   ├── 007-in-process-demo.md     # status: done
│   ├── 008-server-config.md       # status: done
│   ├── 009-app-health.md          # status: done
│   ├── 010-session-api-key.md     # status: done
│   ├── 011-conversation-service.md # status: done
│   ├── 012-conversation-routes.md # status: done
│   ├── 013-event-routes-and-run.md # status: done
│   ├── 014-pubsub.md               # status: done
│   ├── 015-events-websocket.md     # status: done
│   └── 016-local-server-demo.md     # status: done
└── overview.md
```

State lives in the `status:` frontmatter field — **not** in the filename
or folder. Folder placement communicates planning/archival intent.

Optional frontmatter: `feature:` slug, `depends_on:` list of task ids.

## Task file shape

```markdown
---
id: 003-bash-tool
feature: tools          # the feature slug this task belongs to
status: pending         # pending | in-progress | done
depends_on: 
---

# Bash tool

## Migration preflight

Before implementation, inspect the governing ADRs, this task, and its
directly dependent or consuming tasks.
Record the target end-state, temporary legacy bridges, forbidden legacy
dependencies in new code, the removal task for every bridge, and the
architecture test or CI check that enforces the boundary.

## Scope
One atomic, independently-shippable unit of work (1–2 sentences).

## Acceptance criteria
- [ ] ...

## Out of scope
- ...

## Log
### [PA] 2026-06-19 12:30 — Grooming
...
```

## Lifecycle

- **PA** grooming writes the file with `status: pending`.
- **SWE** starts it → `status: in-progress`.
- After the **Tester** PASSES and the task is committed → `status: done`.

Every agent **appends** (never rewrites) a timestamped entry to `## Log`: `### [ROLE] YYYY-MM-DD HH:MM — subject`. Roles: `PA`, `SWE`, `Tester`, `PR Reviewer`, `On-Call`.

Tasks are created and driven by the squid pipelines (`/plan`, `/implement-task`, `/implement-night`).
