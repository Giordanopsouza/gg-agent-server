---
id: 002-domain-types
feature: loop
status: done
depends_on: [001-repo-scaffolding]
---

# Domain types

## Scope

Define the core data shape for a conversation, its status machine, and an event. No persistence and no loop yet.

## Acceptance criteria

- [x] `ConversationStatus` is `idle | running | finished | error` only.
- [x] `Event` has `id`, `seq`, `kind`, `payload`, `created_at`.
- [x] `EventKind` is at least `message | action | observation | status`.
- [x] `ConversationRecord` has `id`, `status`, `working_dir`, `created_at`.
- [x] A unit test rejects an invalid status string at the parse boundary.

## Out of scope

- Writing files to disk (`003`). Running tools (`005`, `006`).

## Log

### [SWE] 2026-08-21 15:37 — Domain types landed

`gg.sdk.domain` with Pydantic models and str enums; exported from `gg.sdk`. `test_domain.py` covers all status variants and rejects `"paused"`.

### [PA] 2026-08-21 13:45 — Grooming

Model the domain first. Status is a state machine, not a pile of flags. Everything later stores and streams these objects.
