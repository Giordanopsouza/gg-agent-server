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

Workspace packages live under `packages/gg-sdk` and `packages/gg-server`.

## Git workflow

One task → one branch → one PR → merge to `main` → delete branch.

1. `git checkout main && git pull --ff-only`
2. `git checkout -b NNN-slug` (match `tasks/NNN-*.md`)
3. Implement, commit, push, open PR, merge
4. Delete the branch; start the next task from fresh `main`

Do not stack tasks on a long-lived branch. Worktrees only for parallel tasks.