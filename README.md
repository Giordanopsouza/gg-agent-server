# gg-agent-server

The shortest mental model is: **control plane manages sandboxes; client SDK provides the interface; server SDK manages conversation state; Pi Agent executes the work.**

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

Three isolated containers start at once. Each Pi clones `Giordanopsouza/personal-website`, does one change (title, background color, or font), opens a pull request, then the sandboxes are removed. No host directory is mounted.

```bash
docker build -t gg-agent-server:dev .
set -a && source .env && set +a
uv run --no-editable python -m gg.sdk.demo.docker_pi_github_pr
```

Needs `OPENROUTER_API_KEY` and a fine-grained `GH_TOKEN` with contents and pull-request write access.

## Docs

- [Architecture](docs/architecture.md)
- [Plan](docs/tasks/overview.md)
- [Task tracker](docs/tasks/README.md)
