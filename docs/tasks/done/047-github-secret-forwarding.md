---
id: 047-github-secret-forwarding
feature: docker
status: done
depends_on: [030-docker-secret-forwarding]
---

# GitHub secret forwarding

## Migration preflight

- **Target end-state:** `DockerWorkspace` can forward a host GitHub token by environment name alongside the OpenRouter key, without placing either value in Docker arguments or persisted data.
- **Temporary legacy bridges:** none; callers that do not request GitHub forwarding behave exactly as before.
- **Forbidden legacy dependencies:** arbitrary environment forwarding, raw token values in command arguments, logs, exceptions, metadata, events, or runtime API requests.
- **Bridge removal task:** n/a; a future secret manager may replace this narrow mechanism.
- **Boundary enforcement:** focused command-construction and failure-path tests assert that only names cross argv and that every forwarded value is redacted from surfaced output.

## Scope

Widen the `secret_env_names` allowlist to accept `GH_TOKEN` and `GITHUB_TOKEN` next to `OPENROUTER_API_KEY`, keeping name-only `--env` forwarding and redacted failure handling.

## Acceptance criteria

- [x] `GH_TOKEN` and `GITHUB_TOKEN` are accepted; any other new name still fails validation.
- [x] Multiple requested secrets forward as independent name-only `--env` entries in one `docker run`.
- [x] A requested but missing or empty host variable fails before `docker run`, naming only the variable.
- [x] Docker argv, object representations, exceptions, and demo output never contain a forwarded token value; redaction covers every requested secret, not just the first.
- [x] Existing OpenRouter forwarding, Docker lifecycle, health, and session-key tests remain green.

## Out of scope

- Generic secrets, credential files, Docker secrets, GitHub App installation tokens, git credential helpers inside the container, runtime `/start` secret plumbing, and cloud vaults.

## Log

### [PA] 2026-09-10 15:35 — Grooming

The GitHub PR demo needs a token inside the sandbox. Extend the narrowest existing credential channel rather than inventing a general secrets system.

### [SWE] 2026-09-10 15:39 — Implementation started

Widening the DockerWorkspace secret allowlist to GH_TOKEN and GITHUB_TOKEN, with tests for multi-name `--env` forwarding, missing-host-variable failure, and redaction of every requested value.

### [Tester] 2026-09-10 15:42 — PASS

Seventeen Docker workspace tests pass, including GitHub name acceptance, one-run multi-secret `--env` forwarding, missing/empty host-variable failure, and redaction of every requested value. Ruff passes repository-wide. The full source suite passes with 198 tests and three opt-in integration tests skipped.

### [SWE] 2026-09-10 15:42 — Complete

`DockerWorkspace` now accepts `GH_TOKEN` and `GITHUB_TOKEN` beside `OPENROUTER_API_KEY`. Forwarding is still name-only `--env`; callers that omit GitHub names are unchanged.
