create table app_private.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  created_at timestamptz not null default now()
);

alter table app_private.profiles enable row level security;

-- The backend sets app.user_id from a verified Auth session with SET LOCAL in
-- the same transaction. Missing context denies access, including to gg_runtime.
grant select, insert, update on app_private.profiles to gg_runtime;
create policy profiles_runtime on app_private.profiles
  for all to gg_runtime
  using (id = nullif(current_setting('app.user_id', true), '')::uuid)
  with check (id = nullif(current_setting('app.user_id', true), '')::uuid);

revoke all on app_private.profiles from anon, authenticated, service_role;
