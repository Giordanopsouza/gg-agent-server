-- A stable, invoker-only helper keeps the transaction-local UUID lookup in
-- one initplan and avoids evaluating current_setting for every profile row.
create function app_private.current_user_id() returns uuid
  language sql stable security invoker
  set search_path = pg_catalog
  as $$ select nullif(current_setting('app.user_id', true), '')::uuid $$;
revoke all on function app_private.current_user_id()
  from public, anon, authenticated, service_role;
grant execute on function app_private.current_user_id() to gg_runtime;

drop policy profiles_runtime on app_private.profiles;
create policy profiles_runtime on app_private.profiles
  for all to gg_runtime
  using (id = (select app_private.current_user_id()))
  with check (id = (select app_private.current_user_id()));

-- Some hosted projects have this Supabase event-trigger helper in public.
-- It does not need to be callable through the Data API.
do $$
begin
  if to_regprocedure('public.rls_auto_enable()') is not null then
    revoke execute on function public.rls_auto_enable()
      from public, anon, authenticated;
  end if;
end $$;
