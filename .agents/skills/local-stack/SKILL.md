---
name: local-stack
description: >-
  Start the local task UI and the runtime control plane, then exercise the
  changed feature in the browser. Use when testing a web or API change,
  running the app locally, or checking the frontend against the backend.
---

# Local stack

The task UI talks to the runtime control plane. `make run` starts `gg.server` on port 8000; that process is not this stack.

| Process | Ready when |
|---|---|
| Backend, `python -m gg.runtime` on `127.0.0.1:8001` | `curl -fsS http://127.0.0.1:8001/health` prints `{"status":"ok"}` |
| Frontend, Vite on `127.0.0.1:5173` | `curl -fsS -o /dev/null -w '%{http_code}' http://127.0.0.1:5173/` prints `200` |

Reuse a process that already meets its ready check. Start only what is down.

## Prepare

From the repo root, run `uv sync --no-editable` when `import gg` fails. In `web/`, run `npm ci` when `node_modules` is missing.

Load the repo env without printing it:

```bash
set -a && source .env && set +a
```

`GG_RUNTIME_API_KEY` must be set and non-empty. Keep the task database out of the worktree:

```bash
export GG_TASK_DB_PATH="${GG_TASK_DB_PATH:-/tmp/gg-tasks.sqlite}"
```

Leave `GG_TASK_DISPATCH_ENABLED` unset unless the feature submits a task that must reach a Modal sandbox.

## Start

Backend, repo root, background:

```bash
uv run --no-editable python -m gg.runtime --host 127.0.0.1 --port 8001
```

Frontend, background. Bind IPv4; a default Vite listen on `[::1]` makes `curl http://127.0.0.1:5173/` fail:

```bash
cd web && npm run dev -- --host 127.0.0.1 --port 5173
```

Vite proxies `/tasks` to `http://127.0.0.1:8001`. `VITE_DEV_API_PROXY` overrides that target and must match the backend port.

Both ready checks above pass before any feature check.

## Exercise

Open `http://127.0.0.1:5173/`. The sidebar stores `GG_RUNTIME_API_KEY` in `localStorage` under `gg.runtime.apiKey`. Enter the same key the runtime process is using. Keep the key out of the URL, commits, and chat.

Walk the changed flow: click, type, submit, navigate. Check every route that shares the changed state, including empty and error states. The browser stays on the Vite origin; `/tasks` is proxied.

For an API-only change, call the route with header `X-API-Key: $GG_RUNTIME_API_KEY`.

## Stop

Leave both processes running while the user is still testing. Stop only the processes this session started when the check is finished.

## Report

Name the URL that answered, the flow you exercised, and anything the browser could not confirm.
