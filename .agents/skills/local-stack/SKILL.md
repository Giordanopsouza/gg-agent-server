---
name: local-stack
description: >-
  Run the React task UI and SQLite gg.runtime locally with a Google session,
  or prove the published Modal origin through a real dispatched task, SQLite
  snapshot, and Modal sandbox container.
---

# Local task stack

Work from the task worktree. `make run` starts the separate sandbox server
`gg.server` on port 8000. `make run-runtime` starts the task API `gg.runtime`
on port 8001. The development UI runs on Vite port 5173. The published runtime
serves the React UI, API, and WebSocket from one Modal HTTPS origin. Follow
`docs/sqlite-modal-operations.md` for local setup and
`docs/sqlite-modal-cutover.md` for the accepted published origin. Do not invent
that URL. The API key and origin in the repo `.env` belong to the local stack
and do not authenticate the published origin.

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

Local and published dispatch both create real sandboxes. Inspect them with the
container commands in the published section. Prove stored state from a snapshot,
not by opening a live database.

If OAuth, credentials, Modal access, or local bind prevent the real run, record
the first unmet prerequisite and the exact boundary tested. Stop only
processes started for this check unless the user is actively testing them.

## Published origin

Use this path to prove the deployed runtime. Read the origin from
`docs/sqlite-modal-cutover.md`.

1. `GET /health` is public and returns status `ok`. `GET /ready` and the task
   routes need `X-API-Key` set to `GG_RUNTIME_API_KEY` from the Modal secret
   `gg-runtime-config` in environment `sqlite-111-proof`. Load that value
   without printing it. The repo `.env` key returns 401 here.

2. Read `GET /tasks/dispatch/status` before submitting. Submit only when
   dispatch is enabled and reconciled and both `reserved` and `pending` are 0.
   This deployment's capacity is 1. One idle workspace blocks every other task.

3. Fulfill a prompt in the published UI with a Google session that already has
   a personal OpenRouter key, plus an authorized repository and base branch when
   the task needs GitHub. `POST /tasks` with the operator key admits an
   ownerless task and still creates a sandbox, but Pi stops with
   `OPENROUTER_API_KEY is required for Pi` because the personal vault key is
   not injected. That proves admission and sandbox creation. It does not prove
   fulfillment. An idle task cannot be cancelled: the API returns 409. The
   reservation stays `running` until 45 minutes without activity, then the
   workspace sleeps and the reservation releases. Do not use an operator task
   to probe this capacity-1 origin when another task needs the slot.

4. The task sandbox is a container of app `gg-agent-sandboxes` in Modal
   environment `main`. The runtime server is a container of app `gg-runtime` in
   environment `sqlite-111-proof`. This CLI has no `modal sandbox` command.

   ```sh
   uv run --no-editable modal container list --env main --json
   uv run --no-editable modal container list --env sqlite-111-proof --json
   ```

   Match the `main` container's start time to `sandbox_creations.sandbox_name`
   and `provider_id` in the snapshot. The row's deployment tag remains
   `sqlite-111-proof`.

5. Prove SQLite with `POST /ops/backup` and the same production API key. Save
   the body outside the repo with mode 0600. Open that file read-only. Require
   `PRAGMA integrity_check` of `ok` and no foreign-key violations. For the new
   task, read `tasks.state`, `task_reservations.phase`,
   `sandbox_creations.provider_state` and `provider_id`,
   `task_results.evidence_complete`, and the event copies. Omit
   `session_api_key` and every credential, session, and vault column. Do not
   open the live database and do not run `db_cli` against the remote runtime.

6. A fulfilled run shows activity events, a response that satisfies the prompt,
   a result manifest, and `reserved: 0` after sleep, with
   `sandbox_cleanup_status` `confirmed_absent`. On 2026-10-12 the operator task
   `eee54a76-3db8-4909-be6f-887a91482d89` reached `idle` with evidence complete,
   a running sandbox in environment `main`, and the only reservation still
   held. Backup revision 156880 passed integrity. The unmet prerequisite for
   prompt fulfillment was a signed-in browser account with a personal
   OpenRouter key.
