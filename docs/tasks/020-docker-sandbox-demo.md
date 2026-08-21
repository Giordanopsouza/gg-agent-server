---
id: 020-docker-sandbox-demo
feature: docker
status: pending
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

- [ ] The demo exits 0.
- [ ] `NOTES.md` exists in the container working_dir, not on the host unless a volume was passed.
- [ ] After the context exits, `docker ps` does not show the demo container.
- [ ] README or the demo docstring names the one line that changed from the local demo: the workspace constructor.

## Out of scope

- Runtime API (`021`). Host bind-mounts as the default path.

## Log

### [PA] 2026-08-21 13:45 — Grooming

Slice 2 checkpoint. If `NOTES.md` lands on your laptop without a volume, you are not in the container. Fix that before slice 3.
