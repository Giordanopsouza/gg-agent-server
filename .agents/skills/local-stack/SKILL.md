---
name: local-stack
description: >-
  Run the task frontend and gg.runtime control plane locally, then exercise a
  changed feature through the real UI or API before shipping it. Use after
  implementing a platform feature or when diagnosing frontend/backend integration.
---

# Local task stack

The task UI talks to `gg.runtime` on port 8001. `make run` starts `gg.server`
on port 8000, which is a different service. Work from the repository root.

## Start and verify

1. Check whether `http://127.0.0.1:8001/health` and
   `http://127.0.0.1:5173/` already respond. Reuse a working process; start
   only what is down. Install missing dependencies with `uv sync --no-editable`
   at the root or `npm ci` in `web/`.
2. For an end-to-end run, load the local credentials without printing them and
   start the control plane with dispatch enabled. Use an isolated database so
   enabling dispatch cannot pick up unrelated queued tasks:

   ```bash
   set -a && source .env && set +a
   GG_LOCAL_DEMO_DIR="$(mktemp -d /tmp/gg-local-stack.XXXXXX)"
   GG_RUNTIME_API_KEY=local-demo \
   GG_TASK_DB_PATH="$GG_LOCAL_DEMO_DIR/tasks.sqlite" \
   GG_TASK_DISPATCH_ENABLED=true \
   GG_TASK_CAPACITY=1 \
   uv run --no-editable python -m gg.runtime --host 127.0.0.1 --port 8001
   ```

   This provisions one Modal sandbox per submitted task. The local `.env`
   needs a working `OPENROUTER_API_KEY`, and Modal must already be configured
   with its app and published image. Do not submit a task until the proxy
   check below succeeds.

3. In a second terminal, run Vite with an explicit local proxy:

   ```bash
   cd web
   VITE_TASK_API_URL= \
   VITE_DEV_API_PROXY=http://127.0.0.1:8001 \
   npm run dev -- --host 127.0.0.1 --port 5173
   ```

   `web/.env.local` can point `VITE_DEV_API_PROXY` at Railway. The explicit
   override prevents a local browser test from calling the remote runtime.
   Keep `VITE_TASK_API_URL` empty so browser requests use Vite's `/tasks`
   proxy.

4. Require all three checks before using the UI:

   ```bash
   curl -fsS http://127.0.0.1:8001/health
   curl -fsS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:5173/
   curl -fsS -o /dev/null -w '%{http_code}\n' \
     -H 'X-API-Key: local-demo' http://127.0.0.1:5173/tasks
   ```

   Expect `{"status":"ok"}`, `200`, and `200`. A `401` from the proxy while
   the backend accepts the key usually means Vite is targeting another
   runtime. Fix that before entering a key or submitting a task in the UI.

If the environment blocks a local bind or loopback request, use its supported
permission escalation. If uv cannot write its default cache, set
`UV_CACHE_DIR` to a writable temporary directory.

## Exercise the changed feature

Open `http://127.0.0.1:5173/` in a browser, enter `local-demo` in the sidebar,
and save it. The UI keeps this key in browser `localStorage` as
`gg.runtime.apiKey`. Walk the changed flow by clicking, typing, submitting,
and navigating. Use a task the sandbox can actually perform. With blank
repository fields, give it a self-contained task such as creating a small file
and reading it back. To validate work on this codebase inside the sandbox,
provide an accessible GitHub repository and base branch, with the needed clone
credential configured. A blank sandbox cannot inspect the local checkout.

Verify the task appears in the sidebar, opens its detail page, and moves
through `queued` and `running` to a terminal state. Require actual activity
events, `result.manifest.agent_outcome`, and a final agent response that
fulfills the prompt. `succeeded` alone is insufficient: an agent can finish
successfully while reporting that it lacked the repository needed for the
requested validation. Confirm `GET /tasks/dispatch/status` has no remaining
reservation after completion. A `check_outcome` of `not_run` means no check
command ran. Check relevant empty and error states when the feature changes
them.

For an admission-only check, explicitly run with
`GG_TASK_DISPATCH_ENABLED=false`; a resulting `queued` task proves UI, proxy,
API, and durable admission only. For an API-only feature, also exercise its
route with `X-API-Key` and verify the response and stored effect.

## Finish

Report the URL, action taken, observed state, and any boundary the check did
not cover. Leave the processes running while the user is testing. Otherwise
stop only processes started for this check.
