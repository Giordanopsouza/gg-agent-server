# ruff: noqa: E501
"""Private GitHub connection state and webhook receipts.

Revision ID: 0003_github_connection
Revises: 0002_task_model
"""

from __future__ import annotations

from alembic import op


revision = "0003_github_connection"
down_revision = "0002_task_model"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in (
        """create table vault_private.github_connections (
            owner_id uuid primary key references app_private.profiles(id) on delete cascade,
            github_user_id bigint not null unique check (github_user_id > 0),
            login text not null,
            token_ciphertext bytea,
            key_version integer not null default 1 check (key_version > 0),
            status text not null check (status in ('connected','pending','revoked')),
            updated_at timestamptz not null default now()
        )""",
        """create table app_private.github_installations (
            owner_id uuid not null references app_private.profiles(id) on delete cascade,
            installation_id bigint not null check (installation_id > 0),
            account_login text not null,
            account_type text not null,
            status text not null check (status in ('active','removed')),
            updated_at timestamptz not null default now(),
            primary key (owner_id, installation_id)
        )""",
        """create index github_installations_id_idx on app_private.github_installations(installation_id)""",
        """create table app_private.github_oauth_flows (
            state_hash bytea primary key,
            owner_id uuid not null references app_private.profiles(id) on delete cascade,
            session_id uuid not null,
            expires_at timestamptz not null
        )""",
        """create index github_oauth_flows_expiry_idx on app_private.github_oauth_flows(expires_at)""",
        """create table app_private.github_webhook_deliveries (
            delivery_id uuid primary key,
            received_at timestamptz not null default now()
        )""",
        """create index github_webhook_deliveries_time_idx on app_private.github_webhook_deliveries(received_at)""",
    ):
        op.execute(statement)
    for table, schema in (
        ("github_connections", "vault_private"),
        ("github_installations", "app_private"),
        ("github_oauth_flows", "app_private"),
        ("github_webhook_deliveries", "app_private"),
    ):
        op.execute(f"alter table {schema}.{table} enable row level security")
        op.execute(
            f"revoke all on {schema}.{table} from public, anon, authenticated, service_role"
        )
    op.execute(
        "grant select, insert, update, delete on vault_private.github_connections to gg_runtime"
    )
    op.execute(
        "grant select, insert, update, delete on app_private.github_installations to gg_runtime"
    )
    op.execute(
        "grant select, insert, delete on app_private.github_oauth_flows to gg_runtime"
    )
    for table in ("github_connections", "github_installations", "github_oauth_flows"):
        schema = "vault_private" if table == "github_connections" else "app_private"
        op.execute(f"""
            create policy {table}_owner on {schema}.{table} for all to gg_runtime
            using (owner_id = nullif(current_setting('app.user_id', true), '')::uuid)
            with check (owner_id = nullif(current_setting('app.user_id', true), '')::uuid)
        """)
    # The runtime role cannot read other owners' rows. Only the signed-webhook
    # handler calls this narrow definer function, after HMAC verification.
    op.execute("""create function app_private.invalidate_github_webhook(
            p_delivery uuid, p_event text, p_action text,
            p_installation bigint, p_github_user bigint
        ) returns boolean language plpgsql security definer
        set search_path = '' as $$
        begin
            insert into app_private.github_webhook_deliveries(delivery_id)
            values (p_delivery) on conflict do nothing;
            if not found then return false; end if;
            if p_event = 'installation' and p_action in ('deleted', 'suspend')
               and p_installation is not null then
                update app_private.github_installations set status = 'removed', updated_at = now()
                where installation_id = p_installation;
            elsif p_event = 'github_app_authorization' and p_action = 'revoked'
               and p_github_user is not null then
                update vault_private.github_connections
                set status = 'revoked', token_ciphertext = null, updated_at = now()
                where github_user_id = p_github_user;
                update app_private.github_installations set status = 'removed', updated_at = now()
                where owner_id in (select owner_id from vault_private.github_connections
                                   where github_user_id = p_github_user);
            end if;
            return true;
        end $$;""")
    op.execute(
        """revoke all on function app_private.invalidate_github_webhook(uuid,text,text,bigint,bigint) from public, anon, authenticated, service_role"""
    )
    op.execute(
        """grant execute on function app_private.invalidate_github_webhook(uuid,text,text,bigint,bigint) to gg_runtime"""
    )


def downgrade() -> None:
    op.execute(
        "drop function app_private.invalidate_github_webhook(uuid,text,text,bigint,bigint)"
    )
    op.execute("drop table app_private.github_webhook_deliveries")
    op.execute("drop table app_private.github_oauth_flows")
    op.execute("drop table app_private.github_installations")
    op.execute("drop table vault_private.github_connections")
