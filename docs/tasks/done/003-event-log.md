---
id: 003-event-log
feature: loop
status: done
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

- [x] `EventLog.append(event)` writes `events/event-{seq:05d}-{id}.json`.
- [x] `EventLog.list()` returns events in `seq` order after a process restart.
- [x] `save_meta` / `load_meta` round-trip `ConversationRecord`.
- [x] `save_base_state` / `load_base_state` round-trip status and working_dir.
- [x] Tests use a temp directory. No shared global path.

## Out of scope

- HTTP (`012`). Pub/sub (`014`). Leases.

## Log

### [SWE] 2026-08-21 16:08 — Event log landed

`gg.sdk.event_log` with `EventLog`, meta/base_state helpers, and `test_event_log.py`. One JSON file per event under `events/`.

### [PA] 2026-08-21 13:45 — Grooming

Match OpenHands layout, not their stale README. One JSON file per event so a crash cannot truncate a jsonl file.
