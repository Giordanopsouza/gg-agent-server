---
id: 002-domain-types
feature: loop
status: pending
depends_on: [001-repo-scaffolding]
---

# Domain types

## Migration preflight

- **Target end-state:** `gg.sdk` exports `ConversationStatus`, `Event`, and `ConversationRecord` as typed models. Illegal combinations do not compile or validate.
- **Temporary legacy bridges:** none.
- **Forbidden legacy dependencies:** booleans like `is_running` plus `is_finished` on the same object.
- **Bridge removal task:** n/a.
- **Boundary enforcement:** status is a str enum or literal union. Tests construct each variant and reject an unknown status string.

## Scope

Define the core data shape for a conversation, its status machine, and an event. No persistence and no loop yet.

## Acceptance criteria

- [ ] `ConversationStatus` is `idle | running | finished | error` only.
- [ ] `Event` has `id`, `seq`, `kind`, `payload`, `created_at`.
- [ ] `EventKind` is at least `message | action | observation | status`.
- [ ] `ConversationRecord` has `id`, `status`, `working_dir`, `created_at`.
- [ ] A unit test rejects an invalid status string at the parse boundary.

## Out of scope

- Writing files to disk (`003`). Running tools (`005`, `006`).

## Log

### [PA] 2026-08-21 13:45 — Grooming

Model the domain first. Status is a state machine, not a pile of flags. Everything later stores and streams these objects.
