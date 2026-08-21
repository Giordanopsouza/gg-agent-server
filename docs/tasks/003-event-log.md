---
id: 003-event-log
feature: loop
status: pending
depends_on: [002-domain-types]
---

# Event log on disk

## Migration preflight

- **Target end-state:** one conversation directory `{conversations_dir}/{id}/` holds `meta.json`, `base_state.json`, and `events/event-{seq:05d}-{id}.json`.
- **Temporary legacy bridges:** none.
- **Forbidden legacy dependencies:** SQLite, a single `events.jsonl` file, in-memory-only logs.
- **Bridge removal task:** n/a.
- **Boundary enforcement:** `EventLog.append` round-trips an `Event` through JSON. A second process can read the same directory.

## Scope

Implement file persistence for conversation metadata, base state, and the append-only event log.

## Acceptance criteria

- [ ] `EventLog.append(event)` writes `events/event-{seq:05d}-{id}.json`.
- [ ] `EventLog.list()` returns events in `seq` order after a process restart.
- [ ] `save_meta` / `load_meta` round-trip `ConversationRecord`.
- [ ] `save_base_state` / `load_base_state` round-trip status and working_dir.
- [ ] Tests use a temp directory. No shared global path.

## Out of scope

- HTTP (`012`). Pub/sub (`014`). Leases.

## Log

### [PA] 2026-08-21 13:45 — Grooming

Match OpenHands layout, not their stale README. One JSON file per event so a crash cannot truncate a jsonl file.
