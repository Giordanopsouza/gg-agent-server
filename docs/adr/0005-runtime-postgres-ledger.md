---
status: accepted
---

# Store durable runtime state in Supabase Postgres

The runtime uses private Supabase Postgres tables for tasks, reservations,
evidence copies, supervision and publication intents. A transaction-scoped
database lock preserves FIFO sequence and global capacity decisions across
connections. The previous local SQLite ledger cannot coordinate separate
runtime processes or survive a host replacement.

The old SQLite files are retained only as offline archives. We do not import
their records into Postgres. This means historical task IDs, events and
results do not appear in the new runtime, and any unresolved external effects
must be reconciled before cutover. Once Postgres accepts a write, restarting
the old SQLite build against its preserved copy would lose new state.
