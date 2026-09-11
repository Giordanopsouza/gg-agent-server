# gg-agent-server

The agent-server does not launch sandboxes. **The sandbox launches the agent-server.** A client starts a Docker container, then talks HTTP and WebSocket to the process already running inside it.

![Background agents](docs/background-agents.png)

## Develop

Python 3.12. Packages live under `packages/gg-sdk` and `packages/gg-server`.

```bash
uv sync --no-editable
uv run pytest
uv run ruff check .
uv run python -m gg.server --host 127.0.0.1 --port 8000
```

Use `uv sync --no-editable`. Default editable installs break `import gg` on Python 3.12.

## Demo

Pi runs inside an isolated container, clones a throwaway GitHub repo, opens a pull request, then the container is removed. No host directory is mounted.

```bash
docker build -t gg-agent-server:dev .
set -a && source .env && set +a
uv run --no-editable python -m gg.sdk.demo.docker_pi_github_pr --repo OWNER/DEMO_REPO
```

Needs `OPENROUTER_API_KEY` and a fine-grained `GH_TOKEN` with contents and pull-request write access.

## Docs

- [Architecture](docs/architecture.md)
- [Plan](docs/tasks/overview.md)
- [Task tracker](docs/tasks/README.md)
