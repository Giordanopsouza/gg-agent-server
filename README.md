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

The control plane starts on port 8001 and requires an explicitly initialized
SQLite database and snapshot, local Google OAuth settings, and a private
`GG_RUNTIME_API_KEY` for operations. Follow the
[local and Modal runbook](docs/sqlite-modal-operations.md) before starting it.
To work on the frontend:

```bash
cd frontend
npm ci
npm run dev
```

`make run` starts the sandbox agent server locally on port 8000.
`make docker-build` builds its image from `sandboxes/Dockerfile`.

## Database migrations

The runtime stores state in local SQLite and publishes validated snapshots to
the Modal Volume. Sequential migrations in
`backend/gg/runtime/sqlite_migrations.py` advance `PRAGMA user_version` and
validate the schema. Google OIDC identifies users by verified `sub` and local
sessions live in the same database. The Modal init, migration, backup, and
restore commands are documented in [the state operations runbook](docs/modal-state-operations.md).

## Docs

- [Component layout decision](docs/adr/0004-component-layout.md)
- [SQLite, Modal and Google decision](docs/adr/0008-sqlite-modal-google.md)
- [Local and published operations](docs/sqlite-modal-operations.md)
- [Task web UI](frontend/README.md)
- [Task tracker](docs/tasks/README.md)
