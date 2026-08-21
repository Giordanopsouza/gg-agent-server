---
id: 023-runtime-api-demo
feature: runtime
status: pending
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

- [ ] `uv run python -m gg.sdk.demo.runtime_notes` exits 0.
- [ ] A sandbox container exists during the run and is gone after.
- [ ] `NOTES.md` is in the sandbox working_dir.
- [ ] Overview or README states that Kubernetes and Cloud would replace only the runtime API process.

## Out of scope

- Billing. Multi-tenant quotas. Warm pools.

## Log

### [PA] 2026-08-21 13:45 — Grooming

Slice 3 checkpoint. Stop after this. You have local, Docker, and "cloud" as one server plus two launchers plus one provisioner.
