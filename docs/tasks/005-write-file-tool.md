---
id: 005-write-file-tool
feature: loop
status: pending
depends_on: [002-domain-types, 004-local-workspace]
---

# Write-file tool

## Migration preflight

- **Target end-state:** a tiny tool registry with one tool, `write_file`, that calls `LocalWorkspace.write_file` and returns an observation payload.
- **Temporary legacy bridges:** none.
- **Forbidden legacy dependencies:** LLM SDKs, a plugin marketplace, shell-as-the-only-tool.
- **Bridge removal task:** n/a.
- **Boundary enforcement:** tools take domain types, not FastAPI request objects.

## Scope

Add a tool protocol and a `write_file` implementation the dummy agent can call.

## Acceptance criteria

- [ ] `Tool` has `name`, `run(args, workspace) -> Observation`.
- [ ] `write_file` args are `path` and `content`.
- [ ] A successful run leaves the file on disk and returns an observation payload.
- [ ] Unknown tool names fail at the registry, not inside the workspace.

## Out of scope

- Shell tool. Browser. The agent loop that *chooses* the tool (`006`).

## Log

### [PA] 2026-08-21 13:45 — Grooming

One tool is enough to prove the loop. A shell tool can wait. You are learning action then observation, not Unix.
