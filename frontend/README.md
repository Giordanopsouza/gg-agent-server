# Task web UI

Small React UI for the authenticated `gg.runtime` Task API. It uses the web
session cookie, submits tasks, and polls durable event copies with
`after=<cursor>`.

## Run locally

Start the control plane as described in the [root README](../README.md). Its
default URL is `http://127.0.0.1:8001`. Then:

```bash
cd frontend
npm ci
npm run dev
```

Open the Vite URL and sign in with Google. The sidebar then shows the personal
OpenRouter key and GitHub connection. Choose a model, authorized repository,
and branch in the task form. The OpenRouter key is sent to the vault API and is
never stored in browser storage. With the default setup, Vite proxies `/tasks`
and `/auth` to `http://127.0.0.1:8001`, so the browser stays on one origin.
For local OAuth and mutation requests, set `GG_WEB_ORIGIN` to the exact Vite
origin (for example `http://127.0.0.1:5173`) and configure the Supabase and
GitHub callback URLs for that origin. The backend must have its Auth, GitHub
App, Postgres, and vault settings configured.

## Configuration

- `VITE_DEV_API_PROXY`: development proxy target. Defaults to
  `http://127.0.0.1:8001`.
- `VITE_TASK_API_URL`: browser-visible Task API base URL, set at build time.
  Omit it when serving UI and API behind one origin with `/tasks` and `/auth`
  routed to the control plane. A different origin requires credentialed CORS,
  compatible cookie settings, and matching `GG_WEB_ORIGIN` on the backend.
- `GG_RUNTIME_CORS_ORIGINS`: comma-separated exact UI origins allowed by the
  runtime for cross-origin requests, for example
  `https://tasks.example.com,http://localhost:5173`. Configure this on the
  runtime when `VITE_TASK_API_URL` points to a different origin.

Build and verify:

```bash
npm test
npm run build:runtime
npm run preview
```

`build:runtime` copies the static bundle into the `gg.runtime` Python package.
The production runtime serves it at `/` and `/assets` on the same origin as
`/auth` and `/tasks`. Rebuild and commit the bundled files whenever the
frontend changes. Direct navigation uses hash URLs (`#/tasks/<id>`), so no
server fallback route is required.

The API owns task state and results. The UI shows the Task API's lifecycle
state (`queued`, `starting`, `running`, `finalizing`, `completed`, `failed`, or
`cancelled`) and uses `manifest.agent_outcome` for completed tasks when it is
available (`succeeded`, `no_changes`, and so on). The follow-up composer is
intentionally read-only in this version.
