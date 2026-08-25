# gg-agent-server

Learning clone of the OpenHands agent-server. The upstream tree this is based on lives at `../software-agent-sdk`.

## Read

- [Architecture](docs/architecture.md) explains the sandbox inversion and package graph. Open it in the editor preview so the diagrams render.
- Start with the [plan overview](docs/tasks/overview.md) for slices and verification, then walk the numbered files in the [task tracker](docs/tasks/README.md).

Diagram sources:

- [docs/diagrams/deployment.mmd](docs/diagrams/deployment.mmd)
- [docs/diagrams/conversation-loop.mmd](docs/diagrams/conversation-loop.mmd)
- [docs/diagrams/packages.mmd](docs/diagrams/packages.mmd)

## Develop

```bash
uv sync
uv run pytest
uv run ruff check .
```

Workspace packages live under `packages/gg-sdk` and `packages/gg-server`.

## Git workflow

One task → one branch → one PR → merge to `main` → delete branch.

1. Implement, commit, push, open PR, merge
2. Delete the branch; start the next task from fresh `main`
