# SQLite runtime: local development and public Modal URL

Work from the dedicated worktree. `gg.server` is the sandbox agent server on
port 8000 (`make run`); `gg.runtime` is the task API on port 8001
(`make run-runtime`). Vite serves the development UI on port 5173 and explicitly
proxies API, auth and WebSocket requests to 8001. The published Modal Server
serves React, API and WebSocket from one HTTPS origin, with no production Node
server. The [state operations runbook](modal-state-operations.md) covers Volume
leases, migration, backup, restore and `recreate` deployment.

## Local first run

Use private paths outside the checkout for DB, snapshot and secrets. Initialize
only once; `init` refuses existing state. Set these in your private environment
without printing their values: `GG_RUNTIME_API_KEY`, `GG_GOOGLE_CLIENT_ID`,
`GG_GOOGLE_CLIENT_SECRET`, `GG_WEB_COOKIE_KEY`, `GG_OPENROUTER_VAULT_KEY`,
`GG_GITHUB_CONNECTION_KEY`, GitHub App credentials, and Modal credentials/image
for dispatch. `GG_WEB_ORIGIN` must equal the Vite origin. The Google and GitHub
callback registrations must be exactly that origin plus
`/auth/google/callback` and `/auth/github/callback`. On loopback only,
`GG_WEB_COOKIE_SECURE=false` permits HTTP cookies; published HTTPS keeps it
true. No administrative key belongs in browser storage.

```sh
uv sync --no-editable
export GG_RUNTIME_DB_PATH=/private/path/runtime.db
export GG_RUNTIME_SNAPSHOT_PATH=/private/path/runtime.snapshot
export GG_WEB_ORIGIN=http://127.0.0.1:5173
export GG_WEB_COOKIE_SECURE=false
uv run --no-editable python -m gg.runtime.db_cli init \
  --db "$GG_RUNTIME_DB_PATH" --snapshot "$GG_RUNTIME_SNAPSHOT_PATH"
GG_TASK_DISPATCH_ENABLED=true make run-runtime
```

In another terminal, run `make frontend-install` once, then start Vite with an
explicit proxy so a private `.env.local` cannot silently select another API:

```sh
VITE_DEV_API_PROXY=http://127.0.0.1:8001 make frontend-dev
```

Check `/health` on 8001 and `/health` through Vite, then sign in through the
Vite URL. Configure personal OpenRouter and GitHub connections in Settings;
choose an authorized repository and branch. Before enabling dispatch, inspect
the current queue for unrelated tasks. A real demo must show activity events,
a response fulfilling its prompt, result manifest/check outcome, and a
released reservation in `/tasks/dispatch/status`. Admission or a terminal
label alone does not prove execution. Local dispatch creates real Modal
sandboxes and needs a published sandbox image and working personal credentials.

For offline database maintenance, stop `gg.runtime` first. Use
`uv run --no-editable python -m gg.runtime.db_cli --help`; `restore` always
targets a fresh DB path and never overwrites the source. Do not copy a live
WAL file or mistake a failed snapshot publication for a rolled-back local
transaction.

## Public onboarding

Run `make modal-init` in the chosen Modal environment before its first deploy,
then `make modal-deploy` and copy the HTTPS URL printed by the command. Set
`GG_WEB_ORIGIN` in the environment's `gg-runtime-config` Secret to that exact
origin and register the exact Google and GitHub callback URLs and GitHub
webhook URL (`/webhooks/github`) with the providers. For the eventual public
launch, confirm the Google OAuth app's production configuration. The user
decided on 2026-10-08 to retain **External / Testing** for current personal
use and defer OAuth publication. The current `openid email` login falls under
[Google's basic-authentication exception](https://support.google.com/cloud/answer/15549945?hl=en),
so Testing does not itself require users to be on the test list. This does
not replace real login and isolation checks. Read back public
origin and callback settings without logging secrets, then use
`make modal-rollover` to load changed Secret values and `make modal-verify` for
health, readiness and committed revision. Never infer or invent the Modal URL.

Use two real Google accounts to verify login, logout/revocation and ownership
isolation. Connect OpenRouter and GitHub per account, including a private
authorized repository. Submit a task through the published UI with dispatch
enabled and verify HTTP/WebSocket activity, prompt fulfillment, manifest and
checks, and released reservation. Record URL, observed revisions, account
labels without identifiers, and first unmet prerequisite in
`docs/tasks/evidence/123-modal-onboarding.md`. Keep production cutover and
old-service shutdown for tasks 124–128.

## QA

Run root targets in order after code changes:

```sh
make format-fix
make lint-fix
make format-check
make lint-check
make pre-commit
make unit-tests
make help
make frontend-test
make frontend-build
git diff --check
```
