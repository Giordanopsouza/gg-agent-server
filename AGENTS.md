# gg-agent-server

# Key Principles You Will Respect All Over Your Work

- Keep the design small and concrete. Prefer deleting machinery over adding abstractions that the current learning goal does not need.
- Preserve the package boundary: `gg.sdk` is client-side and never imports `gg.server`; communication across the boundary uses HTTP/WebSocket contracts.
- Keep infrastructure, serving, application, and domain logic loosely separated by responsibility. Shared domain models live in `gg.sdk`; server-only wiring stays in `gg.server` or `gg.runtime`.
- Every task is independently shippable and ends with an automated test or runnable demo proving the real surface.

## Task worktrees

- Before any repository edit, confirm the checkout is the task's dedicated worktree. Reuse it for follow-up turns; otherwise create `./.agents/worktrees/<task-number>-<task-name>` on a branch with that exact identifier before editing.
- Use the task's existing number and a short lowercase hyphenated name. If none is assigned, use the next unused number across `docs/tasks/` and its subdirectories.

# Key Components

- **Backend** — [`backend/`](backend/): control plane API, durable task state,
  and runtime scheduling/supervision. Python package `gg.runtime`. Read
  [`backend/AGENTS.md`](backend/AGENTS.md).
- **Frontend** — [`frontend/`](frontend/): React UI. It calls the backend
  HTTP API directly; it does not import the Python SDK.
- **Sandboxes** — [`sandboxes/`](sandboxes/): Modal image, sandbox agent
  server, Pi execution, and local conversation state. Python package
  `gg.server`. Read [`sandboxes/AGENTS.md`](sandboxes/AGENTS.md).
- **SDK** — [`packages/gg-sdk/`](packages/gg-sdk/): shared Pydantic HTTP
  contracts, Python task client, and CLI. Read
  [`packages/gg-sdk/AGENTS.md`](packages/gg-sdk/AGENTS.md).

## Component dependencies

- `gg-sdk` imports neither `gg.runtime` nor `gg.server`.
- `gg.runtime` communicates with `gg.server` only over HTTP/WebSocket.
- Backend and sandbox both depend on shared `gg.sdk` contracts.
- The root `pyproject.toml` and `uv.lock` own the uv workspace graph.

## Running commands

Run core verbs from the root [`Makefile`](Makefile), which delegates to component Makefiles. `make help` lists the available aggregate and component targets.

Before handing off a code change, run the root Makefile QA sequence in order: `make format-fix`, `make lint-fix`, `make format-check`, `make lint-check`, `make pre-commit`, then `make unit-tests`.

Use `uv sync --no-editable`: editable workspace installs are unreliable here on Python 3.12 because generated `__editable__*.pth` hooks can be skipped. Use `uv run --no-editable ...` for commands outside Makefile targets.

## Infrastructure & external services

- **Git/GitHub** — use `git` locally and `gh` for pull requests, issues, Actions, and demo verification.
- **Persistence** — sandbox conversation state is stored as JSON files inside each execution environment. The Modal background-task control plane (`gg.runtime`) stores durable queueing, reservations, evidence copies, and publication records in Supabase Postgres (`runtime_private`). Do not treat sandbox JSON as the product task store.

# Testing E2E

- **Local server:** run `make run`, then `curl http://127.0.0.1:8000/health`; success is HTTP 200 reporting status `ok`. `GG_SESSION_API_KEYS` is optional on loopback and required before exposing a non-loopback bind.
- **Platform feature:** before claiming a feature complete, use [`.agents/skills/local-stack/SKILL.md`](.agents/skills/local-stack/SKILL.md) with dispatch enabled and exercise a real task through the frontend and `gg.runtime`. Verify activity events, terminal result, and prompt fulfillment; `queued`, admission-only checks, or a `succeeded` label alone are insufficient. If prerequisites block the run, report the first unmet prerequisite and the exact boundary tested.
