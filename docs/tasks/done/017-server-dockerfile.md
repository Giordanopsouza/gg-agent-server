---
id: 017-server-dockerfile
feature: docker
status: done
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

- [x] `docker build` produces an image tagged `gg-agent-server:dev`.
- [x] `docker run --rm -p 8000:8000 gg-agent-server:dev` serves `GET /health`.
- [x] Process in the container listens on `0.0.0.0:8000`.
- [x] Working dir `/workspace/project` exists.

## Out of scope

- The Python launcher that finds a host port (`019`). GPU flags. Multi-stage binary/PyInstaller.

## Log

### [PA] 2026-08-21 13:45 — Grooming

The server is the sandbox. This image is that sentence made physical. Keep it small so the lesson stays visible.

### [SWE] 2026-08-25 12:05 — Implementation

Two-stage Dockerfile: builder runs `uv sync --frozen --no-dev --no-editable --package gg-server`; runtime copies only `/app/.venv`, runs as user `gg`, sets `GG_WORKSPACE_DIR` and `GG_CONVERSATIONS_DIR` under `/workspace`, and starts `python -m gg.server --host 0.0.0.0 --port 8000`. Added `.dockerignore` to keep the build context lean.

Build and run:

```bash
docker build -t gg-agent-server:dev .
docker run --rm -p 8000:8000 gg-agent-server:dev
curl http://127.0.0.1:8000/health
```

### [Tester] 2026-08-25 12:45 — Verified

Image builds and serves `GET /health` on port 8000. Container listens on `0.0.0.0:8000`. `/workspace/project` exists and is writable by user `gg`.
