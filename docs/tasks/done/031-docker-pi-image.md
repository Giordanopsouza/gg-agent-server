---
id: 031-docker-pi-image
feature: docker
status: done
depends_on: [017-server-dockerfile]
---

# Docker Pi image

## Migration preflight

- **Target end-state:** the existing non-root agent-server image contains pinned Node and Pi executables ready for `PiRpcAgent` to spawn.
- **Temporary legacy bridges:** none; the image entrypoint and Python dependency build remain unchanged.
- **Forbidden legacy dependencies:** unpinned npm installs, runtime downloads, embedded credentials, copied host Pi state, or an ACP adapter.
- **Bridge removal task:** n/a.
- **Boundary enforcement:** build-time version checks plus existing image health and dummy-agent integration tests.

## Scope

Add a Node build stage, install the pinned Pi package, and copy its runtime into the current Python image without changing the server entrypoint or security user.

## Acceptance criteria

- [x] The Dockerfile uses `node:22.23.1-bookworm-slim` as the Node/Pi stage.
- [x] It installs `@earendil-works/pi-coding-agent@0.83.0` with install scripts disabled.
- [x] The final Python image contains the required Node binary, npm runtime, global modules, and `pi` executable.
- [x] The build runs `node --version` and `pi --version` so missing or mismatched runtime files fail early.
- [x] No API key, `auth.json`, models cache, session data, or other `~/.pi` state is copied into the image.
- [x] The final process still runs as user `gg`, works in `/workspace/project`, and starts `gg.server` with the existing command.
- [x] Image health and dummy-agent tests remain green, and `docker run --rm <image> pi --version` reports the pinned Pi version.

## Out of scope

- ACP, persisted login, automatic Pi updates, provider configuration files, or a different server base image.

## Log

### [PA] 2026-08-25 21:53 — Grooming

Bake the external agent into the sandbox image so session startup is deterministic and never downloads executable code.

### [SWE] 2026-09-07 16:31 — Implementation started

Adding the pinned Node and Pi build stage, copying only the executable runtime
into the existing Python image, and verifying both versions in the final stage.

### [SWE] 2026-09-07 16:44 — Preserve npm executable layout

An initial real image build showed that copying npm-created command symlinks as
individual Docker sources dereferenced the Pi CLI and broke its relative ESM
imports. The final stage now recreates the npm, npx, and Pi symlinks against the
copied global module tree before running the pinned version checks.

### [Tester] 2026-09-07 16:47 — PASS

The image built as `gg-agent-server:task031`. A clean container reported Node
v22.23.1, npm 10.9.8, and Pi 0.83.0 while running as `gg` in
`/workspace/project`, with no `/home/gg/.pi` state. The existing Docker dummy
demo passed and produced `NOTES.md`. The full source suite passes with 184 tests
and two opt-in integration tests skipped; Ruff and `git diff --check` pass.

### [SWE] 2026-09-07 16:47 — Complete

Baked the pinned Pi runtime into the existing non-root Python server image
without changing its entrypoint, workspace, or credential boundary.

### [SWE] 2026-09-07 17:46 — Archived

Moved the completed task into `docs/tasks/done`.
