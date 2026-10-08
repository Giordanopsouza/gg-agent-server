---
name: local-stack
description: >-
  Run the React task UI and SQLite gg.runtime locally with a Google session,
  then prove a changed platform feature through a real dispatched task.
---

# Local task stack

Work from the task worktree. `make run` starts the separate sandbox server
`gg.server` on port 8000. `make run-runtime` starts the task API `gg.runtime`
on port 8001. The development UI runs on Vite port 5173. Follow
`docs/sqlite-modal-operations.md` for local and published settings.

## Start and verify

1. Check whether `http://127.0.0.1:8001/health` and
   `http://127.0.0.1:5173/` already respond; reuse healthy processes. Install
   missing dependencies with `uv sync --no-editable` or
   `make frontend-install`. Use private DB/snapshot paths outside the repo.
   Explicitly initialize once with:

   ```sh
   uv run --no-editable python -m gg.runtime.db_cli init \
     --db "$GG_RUNTIME_DB_PATH" --snapshot "$GG_RUNTIME_SNAPSHOT_PATH"
   ```

   Never initialize over existing state. Startup restores a missing local DB
   only from a valid snapshot. A missing or invalid snapshot fails closed.

2. Load private settings without printing them. `GG_RUNTIME_DB_PATH`,
   `GG_RUNTIME_SNAPSHOT_PATH`, `GG_RUNTIME_API_KEY`, Google client ID/secret,
   cookie and vault keys, GitHub App settings and Modal credentials/image must
   be available. Set `GG_WEB_ORIGIN=http://127.0.0.1:5173` and
   `GG_WEB_COOKIE_SECURE=false` only for loopback HTTP. Register the matching
   Google and GitHub callbacks. Before dispatch, inspect the queue for
   unrelated tasks; start the runtime with
   `GG_TASK_DISPATCH_ENABLED=true make run-runtime` when it is safe. This
   provisions a Modal sandbox per task.

3. In a second terminal, override any private Vite proxy setting explicitly:

   ```sh
   VITE_DEV_API_PROXY=http://127.0.0.1:8001 make frontend-dev
   ```

   Check `/health` on 8001 and through Vite. The browser uses relative URLs,
   so OAuth, cookies, task API and WebSocket share the Vite origin. Do not enter
   the runtime operations key into the UI or browser storage.

## Exercise the feature

Open `http://127.0.0.1:5173/`, sign in through Google and set personal
OpenRouter and GitHub credentials in Settings. Select an authorized repository
and base branch for code tasks; a sandbox cannot inspect the local checkout.
Submit a task the sandbox can perform and verify its activity events, final
agent response, result manifest and checks. Confirm
`GET /tasks/dispatch/status` shows the reservation released. A queued task,
admission-only result or `succeeded` label alone does not prove fulfillment.
For an API-only change, also exercise its route and stored effect.

If OAuth, credentials, Modal access, or local bind prevent the real run, record
the first unmet prerequisite and the exact boundary tested. Stop only
processes started for this check unless the user is actively testing them.
