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
- `supabase/` — Supabase local configuration and the frozen pre-Alembic
  migration history.
- `backend/alembic/` — authoritative application-schema migrations.
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

## Database migrations

The backend uses SQLAlchemy 2.x with the psycopg driver. Alembic owns every new
change to `app_private`, `runtime_private`, and `vault_private`; do not add new
application DDL under `supabase/migrations/`. Supabase still owns Auth and the
Postgres service.

Use a server-only migrator connection, never the `gg_runtime` URL:

```bash
GG_MIGRATION_DATABASE_URL='postgresql://...' make db-current
GG_MIGRATION_DATABASE_URL='postgresql://...' make db-check
GG_MIGRATION_DATABASE_URL='postgresql://...' make db-upgrade
```

Revision `0001_application_baseline` adopts an existing version-7 schema after
validating all required tables, or creates the application schemas in a fresh
Supabase database. It does not drop an adopted schema on downgrade; recovery
from the baseline requires a verified backup. Local `supabase-local-reset`
applies the frozen Supabase history and then records/verifies the Alembic
baseline.

## Docs

- [Architecture](docs/architecture.md)
- [Component layout decision](docs/adr/0004-component-layout.md)
- [SQLAlchemy and Alembic decision](docs/adr/0006-sqlalchemy-alembic.md)
- [Task web UI](frontend/README.md)
- [Task tracker](docs/tasks/README.md)
- [Modal sandboxes](docs/modal-sandboxes.md)
