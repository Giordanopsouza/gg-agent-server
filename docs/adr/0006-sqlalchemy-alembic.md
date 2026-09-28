---
status: accepted
---

# Use SQLAlchemy metadata and Alembic for application schemas

The backend uses one bounded synchronous SQLAlchemy engine over psycopg and
keeps explicit SQL for the ledger's concurrency-sensitive operations. Alembic
is the sole authority for new application-schema changes; the earlier Supabase
SQL migrations remain frozen as history, while Supabase continues to own Auth
and host Postgres. The initial Alembic revision validates and adopts the
existing version-7 schema instead of replaying DDL, so production can move to
the new migration history without rewriting data or weakening the runtime
role.

## Consequences

Schema changes must update SQLAlchemy metadata and include a reviewed Alembic
revision whose `alembic check` is clean. Migrations require a separate
server-only migrator URL; `gg_runtime` remains DML-only. The baseline refuses a
destructive downgrade, so rollback uses a tested database backup or a forward
repair migration.
