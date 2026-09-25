---
id: 001-repo-scaffolding
feature: scaffold
status: done
depends_on: []
---

# Repo scaffolding

## Scope

Create the two packages, the workspace `pyproject.toml`, a passing empty test run, and the import DAG check.

## Acceptance criteria

- [x] `uv sync` works from the repo root.
- [x] `uv run pytest` collects tests from both packages and passes.
- [x] `gg.sdk` is importable and `gg.server` is importable.
- [x] A test fails the build if `gg.sdk` imports `gg.server`.
- [x] Root `README.md` points at `docs/architecture.md` and `docs/tasks/overview.md`.

## Out of scope

- Domain types (`002`). FastAPI (`009`). Dockerfile (`017`).

## Log

### [PA] 2026-08-21 14:30 — Scaffold landed

Root uv workspace with `packages/gg-sdk` and `packages/gg-server`, pytest from both packages plus root `tests/test_import_boundary.py`, ruff, and README develop section.

### [PA] 2026-08-21 13:45 — Grooming

This is the OpenHands four-package lesson, cut to two. Get the DAG in CI before any feature code can violate it.
