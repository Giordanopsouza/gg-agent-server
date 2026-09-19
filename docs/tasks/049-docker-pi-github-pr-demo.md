---
id: 049-docker-pi-github-pr-demo
feature: docker
status: done
depends_on:
  - 032-docker-pi-demo
  - 047-github-secret-forwarding
  - 048-docker-git-tools-image
---

# Docker Pi GitHub PR demo

## Migration preflight

- **Target end-state:** one demo starts three isolated containers. Each Pi clones `Giordanopsouza/personal-website`, applies one change (title, background, or font), opens a pull request with `gh`, and the sandboxes stop.
- **Temporary legacy bridges:** none; the notes demo stays the unpaid-path checkpoint.
- **Forbidden legacy dependencies:** host workspace mounts, git credential helpers in the image, baked `gh auth` state, arbitrary secret forwarding, or required paid-model calls in the default test suite.
- **Bridge removal task:** n/a.
- **Boundary enforcement:** offline doubles cover orchestration and cleanup; the live Docker/model/GitHub smoke test is opt-in.

## Scope

Add `gg.sdk.demo.docker_pi_github_pr` from the existing Docker Pi notes demo. Forward OpenRouter and `GH_TOKEN` by name, start three sandboxes, ask each Pi to clone the personal website and open one PR, prove each PR with `gh pr list`, and always stop every container.

## Acceptance criteria

- [x] The demo defaults `--repo` to `Giordanopsouza/personal-website`, accepts `--image`, and defaults the working directory to `/workspace/project`.
- [x] Host `OPENROUTER_API_KEY` and `GH_TOKEN` are required before `docker run`.
- [x] Three `DockerWorkspace` sandboxes start together with `secret_env_names=["OPENROUTER_API_KEY", "GH_TOKEN"]` and no host volume.
- [x] Each prompt tells Pi to use `gh` (including `gh auth setup-git`), never print secrets, and do exactly one change: title, background color, or font.
- [x] Before teardown, the demo lists open PRs with `gh pr list` inside each container and checks a unique marker per task.
- [x] Each conversation finishes successfully and the context manager removes every container on both success and failure.
- [x] Token values do not appear in Docker argv, metadata, persisted events, exceptions, or demo output.
- [x] Offline tests use workspace/conversation doubles; the live smoke test is opt-in and skips without Docker, image, or keys.
- [x] `.env` is gitignored.

## Out of scope

- Image or `DockerWorkspace` changes, SSH, GitHub App tokens, persisted credential helpers, host mounts, runtime API, or closing/deleting the created PR.

## Log

### [PA] 2026-09-15 09:44 — Grooming

Secret forwarding and git/gh in the image already exist. This task is the notes-demo shape pointed at a throwaway GitHub repo.

### [SWE] 2026-09-15 09:45 — Implementation started

Adding `gg.sdk.demo.docker_pi_github_pr` with name-only OpenRouter and GH_TOKEN forwarding, marker-file plus `gh pr list` proof, and always-on cleanup.

### [Tester] 2026-09-15 09:50 — PASS

Eight offline GitHub PR demo tests pass. The live Docker/model/GitHub smoke is skipped without `GG_RUN_DOCKER_PI_TESTS`. The full suite passes with 197 tests and four opt-in integration tests skipped. Ruff passes repository-wide.

### [SWE] 2026-09-15 09:50 — Complete

Implemented the Docker Pi GitHub PR demo, offline doubles, opt-in live smoke, and `.env` gitignore without changing DockerWorkspace or the image.

### [SWE] 2026-09-15 10:05 — Three website sandboxes

The demo now opens three containers at once against `Giordanopsouza/personal-website`. Each Pi owns one change: title, background color, or font. Proof is still `gh pr list` plus a unique marker per task.
