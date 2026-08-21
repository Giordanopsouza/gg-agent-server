---
id: 019-docker-workspace-launcher
feature: docker
status: pending
depends_on: [017-server-dockerfile, 018-remote-conversation-client]
---

# Docker workspace launcher

## Migration preflight

- **Target end-state:** `DockerWorkspace` runs the image, maps a free host port to 8000, polls `GET /health`, then behaves as `RemoteWorkspace(host=http://127.0.0.1:{port})`.
- **Temporary legacy bridges:** none.
- **Forbidden legacy dependencies:** default bind-mount of the host project. Forcing `api_key=None` while forwarding a session key env into the container. That is the OpenHands bug. Either no key in the container, or the client sends the same key.
- **Bridge removal task:** n/a.
- **Boundary enforcement:** `__exit__` stops the container.

## Scope

Client-side `docker run` plus health wait plus cleanup.

## Acceptance criteria

- [ ] `with DockerWorkspace(image="gg-agent-server:dev") as ws:` yields a workspace with a reachable `host`.
- [ ] Health poll fails fast with a clear error if the container dies.
- [ ] No host directory is mounted unless `volumes=` is passed.
- [ ] If the launcher sets a session key on the server, the client sends that key.
- [ ] Leaving the context stops the container.

## Out of scope

- Apptainer. GPU. Extra ports for VSCode.

## Log

### [PA] 2026-08-21 13:45 — Grooming

Do not copy `DockerWorkspace.api_key = None`. If you forward `GG_SESSION_API_KEYS`, you must send the header. Empty keys plus published port is acceptable for local learning if documented.
