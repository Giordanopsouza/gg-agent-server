---
id: 048-docker-git-tools-image
feature: docker
status: done
depends_on: [031-docker-pi-image]
---

# Docker git tools image

## Scope

Add pinned `git` and `gh` to the final image stage, verify both at build time, and keep the `gg` security user and server entrypoint untouched.

## Acceptance criteria

- [x] The Dockerfile pins the git package and the GitHub CLI version; no `apt-get install git` without a version constraint or equivalent pin.
- [x] The build runs `git --version` and `gh --version` so missing or mismatched tools fail early.
- [x] No token, `gh` config, `~/.gitconfig` credential helper, or SSH key is baked into the image.
- [x] The final process still runs as user `gg`, works in `/workspace/project`, and starts `gg.server` with the existing command.
- [x] `docker run --rm <image> git --version` and `docker run --rm <image> gh --version` report the pinned versions.
- [x] Image health, dummy-agent, and Pi tests remain green.

## Out of scope

- SSH-based git auth, persisted `gh auth login`, credential helpers, GitHub App installation tokens, or a different base image.

## Log

### [PA] 2026-09-10 15:35 — Grooming

Pi already has shell tools inside the container; the image simply lacks the executables. Bake them in pinned so the demo never downloads tools at runtime.

### [SWE] 2026-09-10 15:50 — Implementation started

Pinning Debian `git` and GitHub CLI `2.100.0` in the final image stage, verifying both versions at build time, and leaving the `gg` user and server entrypoint unchanged.

### [Tester] 2026-09-10 16:00 — PASS

The image built as `gg-agent-server:task048`. A clean container reported git 2.39.5 and gh 2.100.0 while running as `gg` in `/workspace/project`, with no `~/.gitconfig`, `~/.ssh`, or `gh` config. Pi still reports 0.83.0. The dummy Docker demo wrote `NOTES.md` and left no running sandbox. The full source suite passes with 200 tests and three opt-in integration tests skipped; Ruff and `git diff --check` pass.

### [SWE] 2026-09-10 16:00 — Complete

Baked pinned `git` 2.39.5 and GitHub CLI 2.100.0 into the existing non-root Python server image without changing its entrypoint, workspace, or credential boundary.
