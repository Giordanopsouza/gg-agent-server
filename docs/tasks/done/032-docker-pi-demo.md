---
id: 032-docker-pi-demo
feature: pi
status: done
depends_on:
  - 029-pi-conversation-api
  - 030-docker-secret-forwarding
  - 031-docker-pi-image
---

# Docker Pi demo

## Migration preflight

- **Target end-state:** one demo proves `RemoteConversation -> gg-server -> Pi RPC` inside an isolated container and cleans up the sandbox afterward.
- **Temporary legacy bridges:** none; the existing dummy Docker demo remains available as an offline checkpoint.
- **Forbidden legacy dependencies:** host workspace mounts, runtime API, ACP, persisted credentials, or required paid-model calls in the default test suite.
- **Bridge removal task:** n/a.
- **Boundary enforcement:** offline doubles cover orchestration and cleanup; the real model/container smoke test is opt-in.

## Scope

Add `gg.sdk.demo.docker_pi_notes`, based on the existing Docker demo, to forward the OpenRouter key by name, request a Pi conversation, verify `PI_NOTES.md` in the container, and always stop the container.

## Acceptance criteria

- [x] The demo accepts `--image`, defaults the working directory to `/workspace/project`, and requires the host's `OPENROUTER_API_KEY`.
- [x] `DockerWorkspace` is created with `secret_env_names=["OPENROUTER_API_KEY"]` and no host volume.
- [x] `RemoteConversation` uses `agent.kind="pi"`, provider `openrouter`, and model `google/gemini-3.7-flash`.
- [x] The prompt contains a unique marker and explicitly requests `/workspace/project/PI_NOTES.md` containing it.
- [x] Before teardown, the demo reads the file with `docker exec`, verifies the marker, and collects message, action, observation, and status events.
- [x] The conversation finishes successfully and the context manager removes the container on both success and failure.
- [x] The key value does not appear in Docker argv, metadata, persisted events, exceptions, or demo output.
- [x] Offline tests use workspace/conversation doubles; the real Docker/model smoke test is opt-in and skips without Docker, image, or key.
- [x] `uv run pytest` and `uv run ruff check .` pass after the task, followed by successful manual local and Docker Pi demos.

## Out of scope

- Host mounts, runtime API, Kubernetes, live streaming, resume, multiple prompts, or additional providers.

## Log

### [PA] 2026-08-25 21:53 — Grooming

Final checkpoint for the local product slice: the same remote-conversation surface now drives a real external agent inside the existing sandbox image.

### [SWE] 2026-09-08 13:30 — Implementation started

Adding `gg.sdk.demo.docker_pi_notes` from the existing Docker demo: name-only OpenRouter forwarding, a Pi remote conversation, container-file proof, and always-on cleanup. Offline doubles cover orchestration; the live Docker/model smoke stays opt-in.

### [Tester] 2026-09-08 13:48 — PASS

The full suite passes with 190 tests and three opt-in integration tests skipped. Ruff passes repository-wide. Focused doubles prove Pi agent forwarding, name-only secret wiring, no host mount, marker verification, event collection, CLI output without the key, and container stop on failure. The local Pi demo and Docker Pi demo both exited zero, wrote `PI_NOTES.md` with the unique marker, and left no running sandbox container.

### [SWE] 2026-09-08 13:48 — Complete

Implemented the Docker Pi notes demo, offline workspace doubles, opt-in live smoke, and setup documentation while keeping credentials out of argv, events, and demo output.
