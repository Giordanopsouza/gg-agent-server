-- Let the runtime confirm revocation without direct access to Auth tables.
create function app_private.web_session_active(p_user_id uuid, p_session_id uuid)
returns boolean
language sql stable security definer
set search_path = ''
as $$
  select exists (
    select 1
    from auth.sessions s
    join auth.users u on u.id = s.user_id
    where s.id = p_session_id
      and s.user_id = p_user_id
      and (s.not_after is null or s.not_after > now())
      and u.deleted_at is null
      and (u.banned_until is null or u.banned_until <= now())
  )
$$;

revoke all on function app_private.web_session_active(uuid, uuid)
  from public, anon, authenticated, service_role;
grant execute on function app_private.web_session_active(uuid, uuid) to gg_runtime;
