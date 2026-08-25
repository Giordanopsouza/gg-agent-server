---
id: 020-docker-sandbox-demo
feature: docker
status: done
depends_on: [019-docker-workspace-launcher, 016-local-server-demo]
---

# Docker sandbox demo

## Migration preflight

- **Target end-state:** `uv run python -m gg.sdk.demo.docker_notes` builds or assumes `gg-agent-server:dev`, starts a container, runs the dummy agent through `RemoteConversation`, and shows `NOTES.md` inside the container filesystem.
- **Temporary legacy bridges:** none.
- **Forbidden legacy dependencies:** talking to a server on the host with `LocalConversation`.
- **Bridge removal task:** n/a.
- **Boundary enforcement:** the demo uses `DockerWorkspace` only.

## Scope

Prove slice 2. Same user code as slice 1, different workspace class.

## Acceptance criteria

- [x] The demo exits 0.
- [x] `NOTES.md` exists in the container working_dir, not on the host unless a volume was passed.
- [x] After the context exits, `docker ps` does not show the demo container.
- [x] README or the demo docstring names the one line that changed from the local demo: the workspace constructor.

## Out of scope

- Runtime API (`021`). Host bind-mounts as the default path.

## Log

### [PA] 2026-08-21 13:45 — Grooming

Slice 2 checkpoint. If `NOTES.md` lands on your laptop without a volume, you are not in the container. Fix that before slice 3.

### [SWE] 2026-08-25 01:00 — Implementation started

Adding the Docker-only remote demo and regression coverage for its container
file check and context-managed cleanup.

### [SWE] 2026-08-25 01:20 — Implementation complete

Added `gg.sdk.demo.docker_notes`. It starts `DockerWorkspace` without a bind
mount, drives the server with `RemoteConversation`, reads `/workspace/project/NOTES.md`
via `docker exec`, and returns only after the workspace context has stopped the
container. The module docstring calls out the constructor swap from the local
demo.

### [Tester] 2026-08-25 01:25 — Verified

Focused tests and lint pass. The real `gg-agent-server:dev` demo exited zero,
printed `NOTES.md` from its container, and the following filtered `docker ps`
was empty. The full suite passes from a fresh temporary current directory:
114 passed (one existing Starlette deprecation warning). Full-repository Ruff
retains seven pre-existing notebook and local-conversation formatting findings;
the new files are clean.
