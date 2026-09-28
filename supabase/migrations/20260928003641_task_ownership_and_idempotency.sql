-- Existing rows remain operator-owned. A web user receives ownership only
-- when the server admits a task from a validated Supabase session.
alter table runtime_private.tasks add column owner_id uuid;
alter table runtime_private.retention_tombstones add column owner_id uuid;

alter table runtime_private.tasks drop constraint tasks_idempotency_key_key;
alter table runtime_private.retention_tombstones
  drop constraint retention_tombstones_pkey;
alter table runtime_private.retention_tombstones
  add constraint retention_tombstones_task_id_key unique (task_id);

create unique index tasks_operator_idempotency
  on runtime_private.tasks (idempotency_key) where owner_id is null;
create unique index tasks_owner_idempotency
  on runtime_private.tasks (owner_id, idempotency_key)
  where owner_id is not null;
create index tasks_owner_seq on runtime_private.tasks (owner_id, seq)
  where owner_id is not null;
create unique index tombstones_operator_idempotency
  on runtime_private.retention_tombstones (idempotency_key)
  where owner_id is null;
create unique index tombstones_owner_idempotency
  on runtime_private.retention_tombstones (owner_id, idempotency_key)
  where owner_id is not null;

-- The runtime uses gg_runtime and applies owner predicates in every
-- user-facing lookup. Direct Data API roles retain no schema or table grants.
revoke all on runtime_private.tasks, runtime_private.retention_tombstones
  from anon, authenticated, service_role;
update runtime_private.schema_meta set value = '7'
  where key = 'schema_version' and value = '6';
