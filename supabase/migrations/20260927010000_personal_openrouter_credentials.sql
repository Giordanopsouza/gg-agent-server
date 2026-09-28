-- Ciphertext is produced by the runtime with a key held outside Postgres.
-- One current credential per owner; replacement increments a monotonic version.
create table vault_private.openrouter_credentials (
  owner_id uuid primary key references app_private.profiles (id) on delete cascade,
  ciphertext bytea,
  key_version integer not null default 1 check (key_version > 0),
  credential_version bigint not null default 1 check (credential_version > 0),
  mask text check (length(mask) <= 32),
  constraint credential_and_mask_together check ((ciphertext is null) = (mask is null)),
  updated_at timestamptz not null default now()
);

alter table vault_private.openrouter_credentials enable row level security;
revoke all on vault_private.openrouter_credentials from public, anon, authenticated, service_role;
grant usage on schema vault_private to gg_runtime;
grant select, insert, update, delete on vault_private.openrouter_credentials to gg_runtime;
create policy openrouter_credentials_runtime on vault_private.openrouter_credentials
  for all to gg_runtime
  using (owner_id = nullif(current_setting('app.user_id', true), '')::uuid)
  with check (owner_id = nullif(current_setting('app.user_id', true), '')::uuid);
