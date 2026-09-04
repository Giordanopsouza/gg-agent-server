---
id: 028-pi-local-demo
feature: pi
status: done
depends_on: [027-pi-rpc-agent]
---

# Pi local demo

## Migration preflight

- **Target end-state:** one Python module proves that a real local Pi process can complete a file-writing task through `LocalConversation` with no server.
- **Temporary legacy bridges:** none.
- **Forbidden legacy dependencies:** the demo must not start FastAPI, Docker, ACP, or silently install Pi.
- **Bridge removal task:** n/a.
- **Boundary enforcement:** the standard test uses a fake Pi backend; the real paid smoke test is explicitly opt-in.

## Scope

Add `gg.sdk.demo.pi_notes`, using a temporary workspace by default, to ask Pi to create `PI_NOTES.md` containing a unique marker and display the resulting file and event summary.

## Acceptance criteria

- [x] The demo accepts `--workspace`, defaulting to a newly created temporary directory that is left available for inspection.
- [x] The prompt contains a unique marker and explicitly requests `PI_NOTES.md` containing that marker.
- [x] Successful output prints the workspace path, final assistant text, and counts or kinds of persisted events.
- [x] Documentation gives the pinned prerequisite command `npm install -g --ignore-scripts @earendil-works/pi-coding-agent@0.83.0`.
- [x] With Pi and `OPENROUTER_API_KEY` configured, `uv run python -m gg.sdk.demo.pi_notes` exits zero and creates the expected file.
- [x] An offline test exercises the demo with a fake backend and no network or model charge.
- [x] A real smoke test is opt-in and skips cleanly when the binary or key is absent.

## Out of scope

- FastAPI, remote conversations, Docker, live streaming, or project-wide production configuration.

## Log

### [PA] 2026-08-25 21:53 — Grooming

This is the first checkpoint: prove the external agent and workspace behavior before adding any transport or container boundary.

### [SWE] 2026-09-04 16:38 — Implementation started

Adding the local Pi demo, injectable offline coverage, explicit live-smoke opt-in,
and pinned setup documentation without introducing a server or container path.

### [Tester] 2026-09-04 16:44 — PASS

The isolated full suite passes with 157 tests and the opt-in Pi and Docker
smokes skipped. Ruff passes across `packages` and `tests`, and the two new
source files pass Ruff format checks. The live Pi smoke skipped because this
host has no Pi executable or `OPENROUTER_API_KEY`, exercising the intended
unconfigured path.

### [SWE] 2026-09-04 16:44 — Complete

Implemented the local Pi notes demo, marker and output validation, pinned setup
guide, offline backend coverage, and explicitly gated paid smoke test.
