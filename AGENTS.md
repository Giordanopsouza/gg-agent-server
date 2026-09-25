# gg-agent-server

# Key Principles You Will Respect All Over Your Work

- Keep the design small and concrete. Prefer deleting machinery over adding abstractions that the current learning goal does not need.
- Preserve the package boundary: `gg.sdk` is client-side and never imports `gg.server`; communication across the boundary uses HTTP/WebSocket contracts.
- Keep infrastructure, serving, application, and domain logic loosely separated by responsibility. Shared domain models live in `gg.sdk`; server-only wiring stays in `gg.server` or `gg.runtime`.
- Every task is independently shippable and ends with an automated test or runnable demo proving the real surface.

## Task worktrees

- For every new task that changes repository files, start in a dedicated Git worktree before editing. Continue using that worktree for follow-up turns on the same task; do not create another one for each turn.
- Store each worktree under `./agents/worktrees/` in the repository, at `./agents/worktrees/<task-number>-<task-name>`. Use the task's existing number and a short lowercase hyphenated name. For tasks without an assigned number, use the next unused number found across `docs/tasks/` and its subdirectories.
- Use the same identifier for the task branch (for example, worktree `076-task-worktrees` on branch `076-task-worktrees`).
- If the current checkout is already the dedicated worktree for this task, keep working there.

# Key Components

- **SDK** — [`packages/gg-sdk/`](packages/gg-sdk/): client library, conversation loop, workspace implementations, Pi backend, and demos. Python library; frozen Pydantic domain models, async I/O, and no imports from `gg.server`. Read [`packages/gg-sdk/AGENTS.md`](packages/gg-sdk/AGENTS.md); deeper conventions: `python-backend`, `uv-python`, `pyproject`, and `ruff-python` specs.
- **Server** — [`packages/gg-server/`](packages/gg-server/): FastAPI agent-server plus the Docker runtime control API. Python service; app factories, lifespan-managed state, typed configuration, and thin HTTP/WebSocket routes. Read [`packages/gg-server/AGENTS.md`](packages/gg-server/AGENTS.md)
## Component dependencies

- `gg-server` depends on `gg-sdk`; `gg-sdk` remains independently importable and never imports server source.
- The root [`pyproject.toml`](pyproject.toml) and [`uv.lock`](uv.lock) own the shared uv workspace dependency graph.

## Running commands

Run core verbs from the root [`Makefile`](Makefile), which delegates to component Makefiles with `$(MAKE) -C packages/<component> <verb>`. `make help` lists the available aggregate and component targets.

Manual QA order: `make format-fix`, `make lint-fix`, `make format-check`, `make lint-check`, `make pre-commit`, then `make unit-tests`.

Use `uv sync --no-editable`: editable workspace installs are unreliable here on Python 3.12 because generated `__editable__*.pth` hooks can be skipped. Use `uv run --no-editable ...` for commands outside Makefile targets.

## Infrastructure & external services

- **Git/GitHub** — use `git` locally and `gh` for pull requests, issues, Actions, and demo verification.
- **Persistence** — sandbox conversation state is stored as JSON files inside each execution environment. The Modal background-task control plane (`gg.runtime`) stores durable queueing, reservations, evidence copies, and publication records in local SQLite on the host (`GG_TASK_DB_PATH`). Do not treat the learning-server JSON layout as the production task store.

# Testing E2E

- **Local server:** run `make run`, then `curl http://127.0.0.1:8000/health`; success is HTTP 200 reporting status `ok`. `GG_SESSION_API_KEYS` is optional on loopback and required before exposing a non-loopback bind.
- **Platform feature:** after implementing each feature, use [`.agents/skills/local-stack/SKILL.md`](.agents/skills/local-stack/SKILL.md) to run the frontend and `gg.runtime` together and exercise a relevant task flow before shipping. Verify events, the result, and whether the agent actually fulfilled the prompt; `queued` and a `succeeded` label alone do not prove that.

