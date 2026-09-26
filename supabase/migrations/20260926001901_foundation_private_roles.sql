-- The migrator owns DDL. The runtime login receives a password out of band.
create role gg_runtime login noinherit;
alter role gg_runtime set statement_timeout = '15s';
alter role gg_runtime set lock_timeout = '5s';
alter role gg_runtime set idle_in_transaction_session_timeout = '15s';

create schema app_private;
create schema runtime_private;
create schema vault_private;

revoke all on schema app_private, runtime_private, vault_private
  from public, anon, authenticated, service_role;
grant usage on schema app_private to gg_runtime;

-- Supabase projects may have public-schema default grants, including older projects.
-- Keep product objects in unexposed schemas and remove access to future objects.
alter default privileges for role postgres in schema app_private, runtime_private, vault_private
  revoke all on tables from public, anon, authenticated, service_role;
alter default privileges for role postgres in schema app_private, runtime_private, vault_private
  revoke all on sequences from public, anon, authenticated, service_role;
alter default privileges for role postgres in schema app_private, runtime_private, vault_private
  revoke execute on functions from public, anon, authenticated, service_role;
