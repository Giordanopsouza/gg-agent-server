# Single-host production operations

This document describes the always-on control plane for Modal background tasks on
one persistent-disk host. It supersedes older guidance that treated the server as
JSON-only with no database. Conversation state inside sandboxes remains JSON
files; durable queueing, reservations, evidence copies, and publication records
live in local SQLite (`GG_TASK_DB_PATH`, default `gg-tasks.sqlite`).

## Service layout

Run exactly **one** worker process per deployment. The runtime holds an exclusive
advisory lock (`GG_DISPATCH_LOCK_PATH` or `<db>.dispatch.lock`). A second local
process fails startup rather than sharing dispatch ownership.

Recommended layout:

| Path | Mode | Purpose |
|---|---|---|
| `/var/lib/gg/tasks.sqlite` | `0600` | Durable control-plane ledger (WAL) |
| `/var/lib/gg/evidence/` | `0700` | Optional filesystem evidence (`GG_TASK_EVIDENCE_DIR`) |
| `/etc/gg/runtime.env` | `0600` | Secrets and non-secret configuration |

Use `deploy/production/gg-runtime.service` and
`deploy/production/Caddyfile.example` as starting points. Terminate TLS at the
reverse proxy; bind the runtime to loopback unless API keys are enforced on all
interfaces.

Graceful shutdown (`SIGTERM`) stops admission, detaches from surviving Modal
sandboxes, and closes SQLite. Do **not** copy `tasks.sqlite-wal` alone during
backup; use the online backup API (below).

## Authentication and secrets

All task, event, message, and result HTTP/WebSocket routes require the runtime
control-plane key via the `X-API-Key` header (`GG_RUNTIME_API_KEY`). Sandbox
session keys are generated per task and stored only in the private ledger; they
are not returned in task records or URLs.

Keep `GG_RUNTIME_API_KEY` and `OPENROUTER_API_KEY` in
environment files or a secret manager—never in images, logs, or task payloads.
Set `GG_GITHUB_CLONE_TOKEN` only when running repository tasks.
Rotate keys by updating the env file, restarting the service, and revoking old
keys in GitHub/Modal as needed.

`GET /health` is a public liveness probe. `GET /ready` requires authentication
and reports database availability, dispatch lock ownership, reconciliation, and
unresolved capacity with categories that distinguish provider outages from
confirmed sandbox loss.

## Storage defaults

| Setting | Default | Environment variable |
|---|---:|---|
| Terminal result retention | 7 days | `GG_TERMINAL_RETENTION_DAYS` |
| Tombstone retention | 90 days | `GG_TOMBSTONE_RETENTION_DAYS` |
| Log/event evidence per task | 10 MiB | `GG_MAX_LOG_EVIDENCE_BYTES` |
| Artifacts per task | 25 MiB | `GG_MAX_ARTIFACT_BYTES` |
| Total evidence | 5 GiB | `GG_MAX_TOTAL_EVIDENCE_BYTES` |
| Minimum free disk | 1 GiB | `GG_MIN_FREE_DISK_BYTES` |

When limits are exceeded, new admissions return HTTP 503 before unsafe writes.
Active or unresolved reservation rows are never evicted. Payload expiry removes
bulky evidence but retains compact idempotency and remote-side-effect tombstones
until the tombstone retention window ends.

## Backup and restore

Create backups while the service is running:

```console
uv run --no-editable python -m gg.runtime.backup_cli backup \
  --db /var/lib/gg/tasks.sqlite \
  --destination /var/backups/gg \
  --evidence-dir /var/lib/gg/evidence
```

Restore by copying the backup bundle to the data directory, setting
`GG_TASK_DISPATCH_ENABLED=false`, starting the runtime, and reconciling Modal
ownership via `GET /tasks/dispatch/status` until provider conditions clear. Only
then re-enable dispatch.

## GitHub bot, Modal, and threat model

Clients submit general work with `prompt` and `idempotency_key`, omitting
`repository` and `base_ref`. To run a repository task, also send `repository`
as `owner/name` and an explicit `base_ref`, and configure
`GG_GITHUB_CLONE_TOKEN` for cloning and draft PR publication. Repository
profiles, allowlists, bootstrap commands, and check commands are not required.
Grant the token access only to the repositories this service should work on.

Modal requires a deployed app (`GG_MODAL_APP_NAME`), published image
(`GG_MODAL_IMAGE_NAME`), and quota for concurrent sandboxes. Defaults request
2 CPU and 4096 MiB memory with five-minute startup and 70-minute provider
lifetime caps; see [Modal sandbox operations](modal-sandboxes.md).

This release targets **trusted internal repositories**. Sandboxed code may
access secrets temporarily forwarded for git or LLM calls; malicious code is not
in scope. Leaked Modal sandboxes or stuck reservations appear in dispatch
status—terminate strays in Modal and restart reconciliation before re-enabling
admission.

## Smoke checks

From the repository root after `uv sync --no-editable`:

```console
make -C packages/gg-server production-smoke-tests
```

The suite covers authenticated task access, readiness ownership, second-process
lock rejection, storage pressure, retention, and online backup restore.
