---
id: 030-docker-secret-forwarding
feature: docker
status: done
depends_on: [019-docker-workspace-launcher]
---

# Docker secret forwarding

## Scope

Add `secret_env_names` to `DockerWorkspace`, restricted to `OPENROUTER_API_KEY`, and forward the inherited host value with Docker's name-only `--env` form.

## Acceptance criteria

- [x] `secret_env_names` is optional and preserves the existing Docker command when omitted.
- [x] `OPENROUTER_API_KEY` is the only accepted name in this version; unsupported names fail validation.
- [x] A requested but missing or empty host variable fails before `docker run`.
- [x] The Docker command contains `--env OPENROUTER_API_KEY` and never contains the key value.
- [x] The Docker subprocess receives the host environment needed for name-only forwarding.
- [x] Error paths, object representations, and test output do not reveal the key.
- [x] Existing Docker lifecycle, health, volume, and session-key tests remain green.

## Out of scope

- Generic secrets, credential files, Docker secrets, persisted Pi login, runtime `/start`, Kubernetes, or cloud vault integration.

## Log

### [PA] 2026-08-25 21:53 — Grooming

Use the smallest credential channel needed for the local Docker proof while keeping secret values out of process arguments.

### [SWE] 2026-09-07 16:13 — Implementation started

Adding an allowlisted, name-only environment forwarding path with host-value
preflight checks and redacted Docker failure handling.

### [Tester] 2026-09-07 16:20 — PASS

Nine focused Docker workspace tests pass. Ruff passes repository-wide, and the
full source suite passes with 181 tests and two opt-in integration tests skipped.

### [SWE] 2026-09-07 16:20 — Complete

Implemented narrow OpenRouter environment forwarding without placing the
credential value in Docker arguments, object state, or surfaced failures.

### [SWE] 2026-09-07 17:46 — Archived

Moved the completed task into `docs/tasks/done`.
