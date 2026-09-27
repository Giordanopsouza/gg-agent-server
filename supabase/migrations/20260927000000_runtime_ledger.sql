-- The runtime ledger is private to the server login. Text timestamps preserve
-- the existing HTTP contract's ISO-8601 representation.
grant usage on schema runtime_private to gg_runtime;

create table runtime_private.schema_meta (
  key text primary key, value text not null
);
insert into runtime_private.schema_meta values ('schema_version', '6');

create table runtime_private.tasks (
  id text primary key, seq bigint not null unique, state text not null,
  idempotency_key text not null unique, repository text not null,
  prompt text not null, base_ref text, base_sha text, retry_of text,
  created_at text not null, updated_at text not null, outcome_detail text,
  check_status text, sandbox_cleanup_status text,
  payload_expired integer not null default 0
);
create index idx_tasks_seq on runtime_private.tasks(seq);

create table runtime_private.sandbox_creations (
  task_id text primary key references runtime_private.tasks(id),
  deployment text not null, sandbox_name text not null, tags_json text not null,
  session_api_key text not null, provider_id text, provider_state text not null,
  detail text, created_at text not null, updated_at text not null,
  unique (deployment, sandbox_name)
);
create table runtime_private.task_reservations (
  task_id text primary key references runtime_private.tasks(id),
  phase text not null, condition text, reserved_at text not null,
  updated_at text not null
);
create index idx_reservations_reserved_at
  on runtime_private.task_reservations(reserved_at);
create table runtime_private.publication_intents (
  task_id text primary key references runtime_private.tasks(id),
  repository text not null, task_branch text not null, base_ref text not null,
  task_marker text not null, commit_sha text, state text not null,
  check_outcome text not null, agent_outcome text not null,
  pr_number bigint, pr_url text, pr_draft integer, pr_author text,
  pr_state text, detail text, created_at text not null, updated_at text not null
);
create table runtime_private.task_supervisions (
  task_id text primary key references runtime_private.tasks(id),
  execution_id text not null, task_branch text not null,
  start_key text not null unique, conversation_id text,
  cancel_requested integer not null default 0,
  tail_gap_possible integer not null default 0,
  created_at text not null, updated_at text not null
);
create table runtime_private.task_event_copies (
  task_id text not null references runtime_private.tasks(id),
  cursor_seq bigint not null, source_id text not null,
  source_seq bigint not null, event_json text not null,
  created_at text not null, primary key (task_id, cursor_seq),
  unique (task_id, source_id, source_seq)
);
create table runtime_private.task_message_receipts (
  task_id text not null references runtime_private.tasks(id),
  message_id text not null, content text not null, status text not null,
  detail text, created_at text not null, updated_at text not null,
  primary key (task_id, message_id)
);
create table runtime_private.task_results (
  task_id text primary key references runtime_private.tasks(id),
  execution_id text, manifest_json text,
  evidence_complete integer not null default 0,
  evidence_detail text, archived_at text
);
create table runtime_private.retention_tombstones (
  idempotency_key text primary key, task_id text not null,
  repository text not null, prompt text not null, base_ref text,
  retry_of text, terminal_state text not null, seq bigint not null,
  created_at text not null, updated_at text not null, remote_effect_json text,
  payload_expired_at text not null, expires_at text not null
);

-- The server receives only data operations; DDL and schema ownership stay
-- with the migration role. The schema is never exposed through PostgREST.
grant select on runtime_private.schema_meta to gg_runtime;
grant select, insert, update, delete on
  runtime_private.tasks,
  runtime_private.sandbox_creations,
  runtime_private.task_reservations,
  runtime_private.publication_intents,
  runtime_private.task_supervisions,
  runtime_private.task_event_copies,
  runtime_private.task_message_receipts,
  runtime_private.task_results,
  runtime_private.retention_tombstones
  to gg_runtime;
revoke all on all tables in schema runtime_private
  from anon, authenticated, service_role;
