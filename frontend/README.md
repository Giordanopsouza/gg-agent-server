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
- `GG_BACKEND_URL`: private backend HTTP URL for the production Node server,
  including port. Locally use `http://127.0.0.1:8001`. On Railway use
  `http://${{gg-runtime.RAILWAY_PRIVATE_DOMAIN}}:8001` as a service reference.
- `PORT`: port listened to by the Node server; defaults to `3000` locally.
- Browser API calls use relative URLs so cookies and OAuth callbacks stay on
  the frontend origin.

Build and verify:

```bash
npm test
npm run build
GG_BACKEND_URL=http://127.0.0.1:8001 npm start
```

From the repository root, `make frontend-install`, `make frontend-test`, and
`make frontend-build` delegate to the frontend Makefile. The last target runs
`build` and produces the `dist/` browser files and `dist-server/` Node files.

Desktop QA: at 768px and 1440px, sign in and confirm the sidebar groups every
task by repository with status and date. Open a task, reload, and confirm it
remains selected. Check empty history, API error, and loading states. Type an
unsent prompt, expire the session, sign in as the same account, and confirm the
draft returns; another account must see an empty composer. Sign out and confirm
the account, history, and draft clear. Tab through links, form controls, and
task history to check focus and labels.

The production Node server serves `dist/` at `/` and `/assets`, exposes
`/web-health`, and forwards `/auth`, `/tasks`, `/webhooks`, `/ready`, and
`/health` to the Python runtime. It also forwards task WebSocket upgrades.
Direct navigation uses hash URLs (`#/tasks/<id>`), so no server fallback route
is required. On Railway, build `gg-web` from `/frontend` using Node 22 and
keep `gg-runtime` building from the repository root for the shared Python
workspace. The frontend public domain is the sole browser origin; the runtime
domain can be removed after the new frontend has passed cutover checks.

The API owns task state and results. The UI shows the Task API's lifecycle
state (`queued`, `starting`, `running`, `finalizing`, `completed`, `failed`, or
`cancelled`) and uses `manifest.agent_outcome` for completed tasks when it is
available (`succeeded`, `no_changes`, and so on). The follow-up composer is
intentionally read-only in this version.
