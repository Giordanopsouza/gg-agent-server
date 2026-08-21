---
id: 017-server-dockerfile
feature: docker
status: pending
depends_on: [009-app-health]
---

# Server Dockerfile

## Migration preflight

- **Target end-state:** an image whose PID 1 is `python -m gg.server --host 0.0.0.0 --port 8000`. User is non-root. `GET /health` works on 8000.
- **Temporary legacy bridges:** none.
- **Forbidden legacy dependencies:** Docker-in-Docker, VSCode, VNC, copying the host workspace by default.
- **Bridge removal task:** n/a.
- **Boundary enforcement:** the image does not contain the client's source as a mounted default. `/workspace/project` exists and is writable.

## Scope

Write a Dockerfile for `gg-server` plus a local build command.

## Acceptance criteria

- [ ] `docker build` produces an image tagged `gg-agent-server:dev`.
- [ ] `docker run --rm -p 8000:8000 gg-agent-server:dev` serves `GET /health`.
- [ ] Process in the container listens on `0.0.0.0:8000`.
- [ ] Working dir `/workspace/project` exists.

## Out of scope

- The Python launcher that finds a host port (`019`). GPU flags. Multi-stage binary/PyInstaller.

## Log

### [PA] 2026-08-21 13:45 — Grooming

The server is the sandbox. This image is that sentence made physical. Keep it small so the lesson stays visible.
