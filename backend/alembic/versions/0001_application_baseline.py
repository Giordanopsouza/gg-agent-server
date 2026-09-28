"""Create or adopt the current private application schemas.

Revision ID: 0001_application_baseline
Revises: None
Create Date: 2026-09-28
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import context, op
from sqlalchemy import text


revision: str = "0001_application_baseline"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EXPECTED_SCHEMA_VERSION = "7"
REQUIRED_TABLES = (
    "app_private.profiles",
    "runtime_private.schema_meta",
    "runtime_private.tasks",
    "runtime_private.sandbox_creations",
    "runtime_private.task_reservations",
    "runtime_private.publication_intents",
    "runtime_private.task_supervisions",
    "runtime_private.task_event_copies",
    "runtime_private.task_message_receipts",
    "runtime_private.task_results",
    "runtime_private.retention_tombstones",
    "vault_private.openrouter_credentials",
)


def _adopt_existing_schema() -> bool:
    connection = op.get_bind()
    existing = connection.execute(
        text("select to_regclass('runtime_private.tasks')")
    ).scalar_one()
    if existing is None:
        return False

    missing = [
        table
        for table in REQUIRED_TABLES
        if connection.execute(
            text("select to_regclass(:table_name)"), {"table_name": table}
        ).scalar_one()
        is None
    ]
    if missing:
        raise RuntimeError(
            "refusing to adopt incomplete application schema; missing: "
            + ", ".join(missing)
        )
    version = connection.execute(
        text(
            "select value from runtime_private.schema_meta where key = 'schema_version'"
        )
    ).scalar_one_or_none()
    if version != EXPECTED_SCHEMA_VERSION:
        raise RuntimeError(
            "refusing to adopt runtime schema version "
            f"{version!r}; expected {EXPECTED_SCHEMA_VERSION!r}"
        )
    return True


def upgrade() -> None:
    if not context.is_offline_mode() and _adopt_existing_schema():
        return

    statements = (
        """
        do $$ begin
          if not exists (select 1 from pg_roles where rolname = 'gg_runtime') then
            create role gg_runtime login noinherit;
          end if;
        end $$
        """,
        "alter role gg_runtime set statement_timeout = '15s'",
        "alter role gg_runtime set lock_timeout = '5s'",
        "alter role gg_runtime set idle_in_transaction_session_timeout = '15s'",
        "create schema if not exists app_private",
        "create schema if not exists vault_private",
        "revoke all on schema app_private, runtime_private, vault_private "
        "from public, anon, authenticated, service_role",
        "grant usage on schema app_private to gg_runtime",
        "alter default privileges for role postgres in schema "
        "app_private, runtime_private, vault_private revoke all on tables "
        "from public, anon, authenticated, service_role",
        "alter default privileges for role postgres in schema "
        "app_private, runtime_private, vault_private revoke all on sequences "
        "from public, anon, authenticated, service_role",
        "alter default privileges for role postgres in schema "
        "app_private, runtime_private, vault_private revoke execute on functions "
        "from public, anon, authenticated, service_role",
        """
        create table app_private.profiles (
          id uuid primary key references auth.users (id) on delete cascade,
          created_at timestamptz not null default now()
        )
        """,
        "alter table app_private.profiles enable row level security",
        "grant select, insert, update on app_private.profiles to gg_runtime",
        "revoke all on app_private.profiles from anon, authenticated, service_role",
        """
        create function app_private.current_user_id() returns uuid
          language sql stable security invoker set search_path = pg_catalog
          as $$ select nullif(current_setting('app.user_id', true), '')::uuid $$
        """,
        "revoke all on function app_private.current_user_id() "
        "from public, anon, authenticated, service_role",
        "grant execute on function app_private.current_user_id() to gg_runtime",
        """
        create policy profiles_runtime on app_private.profiles
          for all to gg_runtime
          using (id = (select app_private.current_user_id()))
          with check (id = (select app_private.current_user_id()))
        """,
        """
        create function app_private.web_session_active(
          p_user_id uuid, p_session_id uuid
        ) returns boolean language sql stable security definer set search_path = ''
        as $$
          select exists (
            select 1 from auth.sessions s
            join auth.users u on u.id = s.user_id
            where s.id = p_session_id and s.user_id = p_user_id
              and (s.not_after is null or s.not_after > now())
              and u.deleted_at is null
              and (u.banned_until is null or u.banned_until <= now())
          )
        $$
        """,
        "revoke all on function app_private.web_session_active(uuid, uuid) "
        "from public, anon, authenticated, service_role",
        "grant execute on function app_private.web_session_active(uuid, uuid) "
        "to gg_runtime",
        """
        create table runtime_private.schema_meta (
          key text primary key, value text not null
        )
        """,
        "insert into runtime_private.schema_meta values ('schema_version', '7')",
        """
        create table runtime_private.tasks (
          id text primary key, seq bigint not null unique, state text not null,
          idempotency_key text not null, repository text not null,
          prompt text not null, base_ref text, base_sha text, retry_of text,
          created_at text not null, updated_at text not null, outcome_detail text,
          check_status text, sandbox_cleanup_status text,
          payload_expired integer not null default 0, owner_id uuid
        )
        """,
        "create index idx_tasks_seq on runtime_private.tasks(seq)",
        "create unique index tasks_operator_idempotency on "
        "runtime_private.tasks (idempotency_key) where owner_id is null",
        "create unique index tasks_owner_idempotency on "
        "runtime_private.tasks (owner_id, idempotency_key) "
        "where owner_id is not null",
        "create index tasks_owner_seq on runtime_private.tasks (owner_id, seq) "
        "where owner_id is not null",
        """
        create table runtime_private.sandbox_creations (
          task_id text primary key references runtime_private.tasks(id),
          deployment text not null, sandbox_name text not null,
          tags_json text not null, session_api_key text not null,
          provider_id text, provider_state text not null, detail text,
          created_at text not null, updated_at text not null,
          unique (deployment, sandbox_name)
        )
        """,
        """
        create table runtime_private.task_reservations (
          task_id text primary key references runtime_private.tasks(id),
          phase text not null, condition text, reserved_at text not null,
          updated_at text not null
        )
        """,
        "create index idx_reservations_reserved_at on "
        "runtime_private.task_reservations(reserved_at)",
        """
        create table runtime_private.publication_intents (
          task_id text primary key references runtime_private.tasks(id),
          repository text not null, task_branch text not null,
          base_ref text not null, task_marker text not null, commit_sha text,
          state text not null, check_outcome text not null,
          agent_outcome text not null, pr_number bigint, pr_url text,
          pr_draft integer, pr_author text, pr_state text, detail text,
          created_at text not null, updated_at text not null
        )
        """,
        """
        create table runtime_private.task_supervisions (
          task_id text primary key references runtime_private.tasks(id),
          execution_id text not null, task_branch text not null,
          start_key text not null unique, conversation_id text,
          cancel_requested integer not null default 0,
          tail_gap_possible integer not null default 0,
          created_at text not null, updated_at text not null
        )
        """,
        """
        create table runtime_private.task_event_copies (
          task_id text not null references runtime_private.tasks(id),
          cursor_seq bigint not null, source_id text not null,
          source_seq bigint not null, event_json text not null,
          created_at text not null, primary key (task_id, cursor_seq),
          unique (task_id, source_id, source_seq)
        )
        """,
        """
        create table runtime_private.task_message_receipts (
          task_id text not null references runtime_private.tasks(id),
          message_id text not null, content text not null, status text not null,
          detail text, created_at text not null, updated_at text not null,
          primary key (task_id, message_id)
        )
        """,
        """
        create table runtime_private.task_results (
          task_id text primary key references runtime_private.tasks(id),
          execution_id text, manifest_json text,
          evidence_complete integer not null default 0,
          evidence_detail text, archived_at text
        )
        """,
        """
        create table runtime_private.retention_tombstones (
          idempotency_key text primary key, task_id text not null unique,
          repository text not null, prompt text not null, base_ref text,
          retry_of text, terminal_state text not null, seq bigint not null,
          created_at text not null, updated_at text not null,
          remote_effect_json text, payload_expired_at text not null,
          expires_at text not null, owner_id uuid
        )
        """,
        "create unique index tombstones_operator_idempotency on "
        "runtime_private.retention_tombstones (idempotency_key) "
        "where owner_id is null",
        "create unique index tombstones_owner_idempotency on "
        "runtime_private.retention_tombstones (owner_id, idempotency_key) "
        "where owner_id is not null",
        "grant usage on schema runtime_private to gg_runtime",
        "grant select on runtime_private.schema_meta to gg_runtime",
        """
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
        to gg_runtime
        """,
        "revoke all on all tables in schema runtime_private "
        "from anon, authenticated, service_role",
        """
        create table vault_private.openrouter_credentials (
          owner_id uuid primary key references app_private.profiles (id)
            on delete cascade,
          ciphertext bytea,
          key_version integer not null default 1 check (key_version > 0),
          credential_version bigint not null default 1
            check (credential_version > 0),
          mask text check (length(mask) <= 32),
          constraint credential_and_mask_together
            check ((ciphertext is null) = (mask is null)),
          updated_at timestamptz not null default now()
        )
        """,
        "alter table vault_private.openrouter_credentials enable row level security",
        "revoke all on vault_private.openrouter_credentials "
        "from public, anon, authenticated, service_role",
        "grant usage on schema vault_private to gg_runtime",
        "grant select, insert, update, delete on "
        "vault_private.openrouter_credentials to gg_runtime",
        """
        create policy openrouter_credentials_runtime
          on vault_private.openrouter_credentials for all to gg_runtime
          using (
            owner_id = nullif(current_setting('app.user_id', true), '')::uuid
          )
          with check (
            owner_id = nullif(current_setting('app.user_id', true), '')::uuid
          )
        """,
    )
    for statement in statements:
        op.execute(statement)


def downgrade() -> None:
    raise RuntimeError(
        "the adopted application baseline cannot be downgraded safely; "
        "restore a verified backup instead"
    )
