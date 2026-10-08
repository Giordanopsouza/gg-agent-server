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

Open the Vite URL and sign in with Google. Open Settings to configure your personal
OpenRouter key and GitHub connection. Home has a centered task composer with a
model picker, optional authorized repository, and branch selector. Submit with
the send button or Cmd/Ctrl+Enter. The OpenRouter key is sent to the vault API and is
never stored in browser storage. With the default setup, Vite proxies `/tasks`
and `/auth` to `http://127.0.0.1:8001`, so the browser stays on one origin.
For local OAuth and mutation requests, set `GG_WEB_ORIGIN` to the exact Vite
origin (for example `http://127.0.0.1:5173`) and configure the Google and
GitHub callback URLs for that origin. The backend must have its Auth, GitHub
App, SQLite, and vault settings configured.

## Configuration

- `VITE_DEV_API_PROXY`: development proxy target. Defaults to
  `http://127.0.0.1:8001`.
- Browser API calls use relative URLs so cookies and OAuth callbacks stay on
  the frontend origin.

Build and verify:

```bash
npm test
npm run build

```

From the repository root, `make frontend-install`, `make frontend-test`, and
`make frontend-build` delegate to the frontend Makefile. The last target runs
`build` and produces `dist/`, served by FastAPI with `GG_WEB_DIST_PATH`.

Desktop QA: at 768px and 1440px, sign in and confirm the sidebar groups every
task by repository with status. Search tasks, collapse workspace groups, and
open the Tasks page to see dates. At 390px, open the navigation drawer and
confirm selecting a page closes it. Open a task, reload, and confirm it
remains selected. Check empty history, API error, and loading states. Type an
unsent prompt, expire the session, sign in as the same account, and confirm the
draft returns; another account must see an empty composer. Sign out and confirm
the account, history, and draft clear. Tab through links, form controls, and
task history to check focus and labels.

Production runs one FastAPI process serving `dist/`, API and WebSockets.
Set `GG_WEB_DIST_PATH` to the absolute build directory and `GG_WEB_ORIGIN`
to the public HTTPS origin (loopback HTTP is allowed for local demos).
Use `GG_RUNTIME_DB_PATH` for the active local SQLite database and
`GG_RUNTIME_SNAPSHOT_PATH` for its validated snapshot; initialize state
explicitly with `python -m gg.runtime.db_cli init` before first startup.
Node is only needed for the Vite build and development proxy.

The API owns task state and results. The UI shows the Task API's lifecycle
state (`queued`, `starting`, `running`, `finalizing`, `completed`, `failed`, or
`cancelled`) and uses `manifest.agent_outcome` for completed tasks when it is
available (`succeeded`, `no_changes`, and so on). The follow-up composer is
intentionally read-only in this version.
