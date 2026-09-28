begin;
set local search_path = extensions, public;
select plan(14);

select ok(to_regclass('vault_private.openrouter_credentials') is not null, 'vault table exists');
select ok((select relrowsecurity from pg_class where oid = 'vault_private.openrouter_credentials'::regclass), 'vault RLS enabled');
select ok(has_schema_privilege('gg_runtime', 'vault_private', 'USAGE'), 'runtime can use vault schema');
select ok(has_table_privilege('gg_runtime', 'vault_private.openrouter_credentials', 'SELECT,INSERT,UPDATE,DELETE'), 'runtime has bounded table access');
select ok(not has_schema_privilege('anon', 'vault_private', 'USAGE'), 'anon cannot use vault schema');
select ok(not has_schema_privilege('authenticated', 'vault_private', 'USAGE'), 'authenticated cannot use vault schema');
select ok(not has_schema_privilege('service_role', 'vault_private', 'USAGE'), 'service role cannot use vault schema');
select ok(not has_table_privilege('anon', 'vault_private.openrouter_credentials', 'SELECT'), 'anon cannot read credentials');
select ok(not has_table_privilege('authenticated', 'vault_private.openrouter_credentials', 'SELECT'), 'authenticated cannot read credentials');
select ok(not has_table_privilege('service_role', 'vault_private.openrouter_credentials', 'SELECT'), 'service role cannot read credentials');
select ok(not has_table_privilege('anon', 'vault_private.openrouter_credentials', 'INSERT,UPDATE,DELETE'), 'anon cannot mutate credentials');
select ok(not has_table_privilege('authenticated', 'vault_private.openrouter_credentials', 'INSERT,UPDATE,DELETE'), 'authenticated cannot mutate credentials');
select ok(not has_table_privilege('service_role', 'vault_private.openrouter_credentials', 'INSERT,UPDATE,DELETE'), 'service role cannot mutate credentials');
select ok(not exists (select 1 from pg_policies where schemaname = 'vault_private' and tablename = 'openrouter_credentials' and roles::text[] && array['anon', 'authenticated', 'public']), 'no public vault policy');

select * from finish();
rollback;
