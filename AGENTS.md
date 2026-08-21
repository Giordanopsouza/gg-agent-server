# gg-agent-server

Learning clone of the OpenHands agent-server. The upstream tree this is based on lives at `../software-agent-sdk`.

## Read

- [Architecture](docs/architecture.md) explains the sandbox inversion and package graph. Open it in the editor preview so the diagrams render.
- [Plan overview](docs/tasks/overview.md) lists slices 1 to 3 and verification commands.
- [Task tracker](docs/tasks/README.md) is one file per atomic task.

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

Workspace packages live under `packages/gg-sdk` and `packages/gg-server`. Task 001 is [repo scaffolding](docs/tasks/001-repo-scaffolding.md).
