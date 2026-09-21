# Railway runtime deployment

The `gg-runtime` service is the single-process control plane. It creates task
sandboxes in Modal; Railway runs only the API, scheduler, and SQLite ledger.
Use a separate Railway project for this shared service. The Docker build context
must be the repository root because `gg-server` depends on `gg-sdk`.

## Service setup

1. Create one Railway service from this repository. Keep the root directory `/`
   and use one replica. The root `Dockerfile` starts `gg.runtime` when
   `GG_RUNTIME_MODE=control-plane`; other Docker and Modal demos still launch
   `gg.server`. Set the deployment health check to `/health`.
2. Attach a persistent volume at `/var/lib/gg`. Railway mounts volumes as root,
   while the image defaults to user `gg`. Writing the SQLite ledger on that
   volume requires an approved access strategy before task dispatch is enabled.
   `RAILWAY_RUN_UID=0` runs the entire service as root and needs an explicit
   security decision. Mounting a volume causes a brief interruption during
   redeploy; the scheduler reconciles surviving Modal sandboxes after restart.
   Size the volume above the configured minimum free space and evidence
   retention limits.
3. Set these service variables:

   | Variable | Value |
   |---|---|
   | `PORT` | `8001` |
   | `GG_RUNTIME_MODE` | `control-plane` |
   | `GG_RUNTIME_API_KEY` | independent random secret shared only with trusted clients |
   | `GG_TASK_DB_PATH` | `/var/lib/gg/tasks.sqlite` |
   | `GG_TASK_EVIDENCE_DIR` | `/var/lib/gg/evidence` |
   | `GG_DISPATCH_LOCK_PATH` | `/var/lib/gg/tasks.sqlite.dispatch.lock` |
   | `GG_TASK_DISPATCH_ENABLED` | `false` until live smoke and credentials pass |
   | `GG_MODAL_APP_NAME` | deployed Modal app name |
   | `GG_MODAL_IMAGE_NAME` | published, versioned Modal image name |
   | `GG_MODAL_DEPLOYMENT` | unique name for this control plane |
   | `GG_REPOSITORY_ALLOWLIST` | comma-separated trusted `owner/repo` names |
   | `GG_REPOSITORY_PROFILES_PATH` | `/app/config/repository-profiles.json` |
   | `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET` | Modal workspace token |
   | `GG_GITHUB_CLONE_TOKEN` | fine-grained GitHub bot token |
   | `OPENROUTER_API_KEY` | agent inference key |

   Add `config/repository-profiles.json` with the approved repositories and
   their bootstrap and check commands before enabling dispatch. Do not put
   secrets in that file. `config/repository-profiles.example.json` shows its
   shape. The file is copied into the Docker image at build time.
4. Generate a Railway domain for the service. The task API requires `X-API-Key`;
   `/health` is public, and `/ready` is authenticated. Give each consuming app
   the URL and key through its service variables, never its agent prompt.

## Verification

After deployment, confirm `GET /health` returns `{"status":"ok"}` and
authenticated `GET /ready` reports ready. Run
`make -C packages/gg-server production-smoke-tests` before release. Publish the
Modal image with `uv run --no-editable python -m gg.runtime.modal_image` and run
the opt-in Modal smoke in [Modal sandbox operations](modal-sandboxes.md). Then
submit one scoped task against a disposable allowlisted repository, inspect
`GET /tasks/{id}/result`, confirm the draft PR link, and check
`GET /tasks/dispatch/status` for completed sandbox cleanup. Enable
`GG_TASK_DISPATCH_ENABLED=true` only after that succeeds.

The ten-sandbox capacity claim requires the separate live acceptance in
[task 060](tasks/060-ten-sandbox-production-acceptance.md).
