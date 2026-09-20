# gg-agent-server

# Key Principles You Will Respect All Over Your Work

- Keep the design small and concrete. Prefer deleting machinery over adding abstractions that the current learning goal does not need.
- Preserve the package boundary: `gg.sdk` is client-side and never imports `gg.server`; communication across the boundary uses HTTP/WebSocket contracts.
- Keep infrastructure, serving, application, and domain logic loosely separated by responsibility. Shared domain models live in `gg.sdk`; server-only wiring stays in `gg.server` or `gg.runtime`.
- Every task is independently shippable and ends with an automated test or runnable demo proving the real surface.

# Key Components

- **SDK** — [`packages/gg-sdk/`](packages/gg-sdk/): client library, conversation loop, workspace implementations, Pi backend, and demos. Python library; frozen Pydantic domain models, async I/O, and no imports from `gg.server`. Read [`packages/gg-sdk/AGENTS.md`](packages/gg-sdk/AGENTS.md); deeper conventions: squid `python-backend`, `uv-python`, `pyproject`, and `ruff-python` specs.
- **Server** — [`packages/gg-server/`](packages/gg-server/): FastAPI agent-server plus the Docker runtime control API. Python service; app factories, lifespan-managed state, typed configuration, and thin HTTP/WebSocket routes. Read [`packages/gg-server/AGENTS.md`](packages/gg-server/AGENTS.md); deeper conventions: squid `python-backend` and `fastapi-service` specs.

## Component dependencies

- `gg-server` depends on `gg-sdk`; `gg-sdk` remains independently importable and never imports server source.
- The root [`pyproject.toml`](pyproject.toml) and [`uv.lock`](uv.lock) own the shared uv workspace dependency graph.

# Tech Stack

Each package manifest and Makefile are authoritative for dependencies and commands. Python 3.12, uv workspaces, Pydantic, FastAPI, pytest, Ruff, Docker, and the Pi coding agent are the current stack.

## Running commands

Run core verbs from the root [`Makefile`](Makefile), which delegates to component Makefiles with `$(MAKE) -C packages/<component> <verb>`. `make help` lists the available aggregate and component targets.

Manual QA order: `make format-fix`, `make lint-fix`, `make format-check`, `make lint-check`, `make pre-commit`, then `make unit-tests`.

Use `uv sync --no-editable`: editable workspace installs are unreliable here on Python 3.12 because generated `__editable__*.pth` hooks can be skipped. Use `uv run --no-editable ...` for commands outside Makefile targets.

## Infrastructure & external services

- **Git/GitHub** — use `git` locally and `gh` for pull requests, issues, Actions, and demo verification.
- **Docker** — build the sandbox image with `make docker-build`; runtime tests are opt-in through the pytest markers declared in `pyproject.toml`.
- **Persistence** — conversation state is stored as JSON files; this project has no database.

# Developing New Features & Bug Fixes

This project uses the squid agent team and a file tracker at [`docs/tasks/`](docs/tasks/). `TRACKER_MODE: file`: state lives in each task's `status:` frontmatter; completed work moves to `docs/tasks/done/`, and every role appends to the task log.

One task → one branch → one PR → merge to `main` → delete the branch. Start the next task from fresh `main`. 

# Testing E2E

- **Local server:** run `make run`, then `curl http://127.0.0.1:8000/health`; success is HTTP 200 reporting status `ok`. `GG_SESSION_API_KEYS` is optional on loopback and required before exposing a non-loopback bind.
- **Docker/GitHub demo:** export `OPENROUTER_API_KEY` and a fine-grained `GH_TOKEN`, run `make docker-build`, then `make demo-docker-pr`; success is three isolated sandboxes opening their pull requests and all containers being removed.
