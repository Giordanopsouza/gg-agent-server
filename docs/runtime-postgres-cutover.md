# Runtime Postgres cutover

Task 078 replaces the runtime's durable SQLite ledger with tables in the
unexposed `runtime_private` Supabase Postgres schema. `GG_RUNTIME_DATABASE_URL`
is required at startup. There is no SQLite fallback. The previous local SQLite
files are not imported. Any task,
event, result, reservation or publication present only in SQLite will not
appear in the Postgres runtime.

## Before enabling writes

1. On the current Supabase Free plan, take a fresh logical database export
   with `supabase db dump` or `pg_dump`, store it encrypted off site, record
   its timestamp and retention, and restore it into a separate database to
   verify recovery. Free projects have no managed daily backup or PITR.
   Save filesystem evidence separately if `GG_TASK_EVIDENCE_DIR` is configured.
   See [Supabase Database Backups](https://supabase.com/docs/guides/platform/backups).
2. Disable HTTP task admission and set `GG_TASK_DISPATCH_ENABLED=false` on the
   old runtime. Wait for active runs to finish. For each unresolved reservation,
   inspect Modal ownership and PR publication before terminating or handing it
   off. Do not start a second dispatcher against the same Modal deployment.
3. Preserve the old SQLite database and WAL together as an offline archive.
   Export a task/reservation/publication count and record any unfinished IDs.
   The archive is not a source for the new runtime.
4. Apply `20260927000000_runtime_ledger.sql` and verify that `gg_runtime` can
   read/write `runtime_private` while `anon`, `authenticated` and
   `service_role` cannot. Check the Supabase database advisors.
5. Set the server-only `GG_RUNTIME_DATABASE_URL` and start with dispatch still
   disabled. Check `/ready`, create and read a disposable task, restart, and
   confirm that its events and result remain. Reconcile old Modal sandboxes and
   remote PRs manually before enabling dispatch and reopening admission.

There must be no interval where both old SQLite and new Postgres runtimes
admit or dispatch tasks. Before any Postgres write, rollback means stopping the
new runtime and starting the preserved SQLite build and data. Once Postgres has
accepted a task, do not reopen the old SQLite copy: use a forward fix or an
explicitly rehearsed reverse migration that includes all new records.

## Ongoing recovery

The Postgres transaction lock protects admission sequence, idempotency,
capacity claims, and publication intents across connections. An interrupted
transaction rolls back without consuming a task or reservation. On restart,
the scheduler reconciles durable reservations with Modal before dispatching.
Monitor `/ready` and `/tasks/dispatch/status`; unresolved creation or cleanup
keeps capacity reserved until ownership is established. Restore the logical
export to a separate database first, compare task and evidence counts, and
reconcile external Modal/GitHub effects before any production restore. If the
project later moves to a paid plan, verify the actual managed backup policy
before relying on it.
