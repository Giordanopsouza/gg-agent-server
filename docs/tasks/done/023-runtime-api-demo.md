---
id: 023-runtime-api-demo
feature: runtime
status: done
depends_on: [022-runtime-workspace-client, 020-docker-sandbox-demo]
---

# Runtime API demo

## Migration preflight

- **Target end-state:** one command starts the runtime API, which starts a sandbox container, which runs the dummy agent. `NOTES.md` appears in that container. Both processes clean up.
- **Temporary legacy bridges:** none.
- **Forbidden legacy dependencies:** a real cloud account. A kubeconfig.
- **Bridge removal task:** n/a.
- **Boundary enforcement:** the demo file should look like the Docker demo with `RuntimeWorkspace(...)` instead of `DockerWorkspace(...)`.

## Scope

Prove slice 3 end to end.

## Acceptance criteria

- [x] `uv run python -m gg.sdk.demo.runtime_notes` exits 0.
- [x] A sandbox container exists during the run and is gone after.
- [x] `NOTES.md` is in the sandbox working_dir.
- [x] Overview or README states that Kubernetes and Cloud would replace only the runtime API process.

## Out of scope

- Billing. Multi-tenant quotas. Warm pools.

## Log

### [PA] 2026-08-21 13:45 — Grooming

Slice 3 checkpoint. Stop after this. You have local, Docker, and "cloud" as one server plus two launchers plus one provisioner.

### [SWE] 2026-08-25 17:50 — Implementation started

Adding a one-command demo that starts the standalone runtime process, provisions
the sandbox only through `RuntimeWorkspace`, proves `NOTES.md` inside the new
container, and verifies both the sandbox and runtime process are cleaned up.

### [SWE] 2026-08-25 18:03 — Implementation complete

Added `gg.sdk.demo.runtime_notes`, which launches the standalone runtime API,
provisions only through `RuntimeWorkspace`, identifies the newly created
sandbox for proof, reads `NOTES.md` inside it, and verifies context-managed
sandbox and subprocess cleanup. Added focused lifecycle and import-boundary
coverage plus the Cloud/Kubernetes provisioner boundary to the overview.

### [Tester] 2026-08-25 18:05 — Verified

The exact demo command exited zero against `gg-agent-server:dev`, printed the
note from `/workspace/project/NOTES.md`, stopped its session, and shut down the
runtime API. A post-run Docker query found no matching container. The clean-cwd
suite passes with 136 tests and one opt-in Docker test skipped. New files pass
Ruff; full-repository Ruff retains the seven pre-existing findings documented
by earlier tasks.
