---
id: 004-local-workspace
feature: loop
status: pending
depends_on: [002-domain-types]
---

# Local workspace

## Migration preflight

- **Target end-state:** `LocalWorkspace` reads and writes files under `working_dir` and runs a subprocess with that cwd.
- **Temporary legacy bridges:** none.
- **Forbidden legacy dependencies:** HTTP, Docker, path sandboxing that pretends to be isolation.
- **Bridge removal task:** n/a.
- **Boundary enforcement:** missing `working_dir` is created on start. Tests never touch the repo root.

## Scope

Implement the in-process workspace: mkdir, write, read, and `execute_command` with cwd defaulting to `working_dir`.

## Acceptance criteria

- [ ] `write_file(relative_or_absolute, content)` creates parent dirs and writes bytes.
- [ ] `read_file` returns the bytes just written.
- [ ] `execute_command("pwd")` with no cwd runs inside `working_dir`.
- [ ] Tests use a temp directory and assert the file exists on disk.

## Out of scope

- Remote HTTP workspace (`018`). Docker volumes (`019`). A jail that blocks `..`. Isolation waits for the container in slice 2.

## Log

### [PA] 2026-08-21 13:45 — Grooming

Local `execute_command` defaults cwd to `working_dir`. Remember this when you later write the remote client. OpenHands remote does not default that way.
