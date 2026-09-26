# gg-agent-server

The control plane manages tasks and sandboxes. Each sandbox runs a Pi agent.
The Python SDK supplies shared contracts and a task client; the React frontend
calls the control plane API directly.

## Repository map

- `backend/` — the control plane (`gg.runtime`): task API, durable state,
  scheduling, Modal lifecycle, supervision, and publication. Its runtime
  modules are part of this backend deployment.
- `frontend/` — the React task UI. It uses HTTP through `src/api.ts`.
- `sandboxes/` — the per-task image and agent server (`gg.server`), including
  Pi, local workspaces, and conversation persistence.
- `packages/gg-sdk/` — shared Pydantic HTTP contracts, Python task client,
  and `gg-task` CLI. It imports neither backend nor sandbox code.
- `supabase/` — database configuration and migrations.
- `scripts/` — operational smoke checks.
- `docs/` — architecture, decisions, and task history.
- `tests/` — repository-wide boundary and image checks.

The backend calls the sandbox server over HTTP/WebSocket contracts. The
sandbox and backend both use `gg.sdk` models. Runtime data such as conversation
files belongs outside source control for new runs; existing tracked
`workspace/` fixtures are preserved until their purpose is confirmed.

## Develop

Use Python 3.12 and Node 22.

```bash
uv sync --no-editable
make unit-tests
make lint-check
make format-check
make run-runtime
```

The control plane starts on port 8001. To work on the frontend:

```bash
cd frontend
npm ci
npm run dev
```

`make run` starts the sandbox agent server locally on port 8000.
`make docker-build` builds its image from `sandboxes/Dockerfile`.

## Docs

- [Architecture](docs/architecture.md)
- [Component layout decision](docs/adr/0004-component-layout.md)
- [Task web UI](frontend/README.md)
- [Task tracker](docs/tasks/README.md)
- [Modal sandboxes](docs/modal-sandboxes.md)
