# Supabase foundation (task 077)

## Environments and promotion

| Environment | Project | Data |
| --- | --- | --- |
| Local | Docker project `gg-agent-server` | Disposable synthetic Auth users and profiles |
| Production | `xmqpgubedtjirohntdwg` (`GGAgenteServer`) | No synthetic data or destructive reset |

The user chose to use only the existing production project for task 077 after Supabase rejected a separate staging project because the organization owner has two active free projects. Local Supabase is the test environment. Do not reuse the unrelated `wpp-agent` project or insert synthetic test data in production. Do not run `db reset --linked` or `--db-url` on the hosted project.

The CLI is pinned in the root `package-lock.json`. Run `npm ci` and `uv sync --no-editable`, then:

```sh
make supabase-local-start
SUPABASE_RESET_TARGET=gg-agent-server make supabase-integration-tests
SUPABASE_RESET_TARGET=gg-agent-server make supabase-local-reset
```

The reset target accepts only the named local Docker project and invokes `db reset --local` with no remote URL. Integration runs pgTAP grants/RLS tests, real local Auth signup and profile FK checks, a bounded runtime login, a first-migration-to-latest upgrade with a synthetic Auth user, and local security advisors. The synthetic user is removed afterward. Docker Desktop must share the checkout path; if it cannot, copy `supabase/` to a Docker-shared temporary directory and pass `SUPABASE_LOCAL_WORKDIR` to the Make targets. Keep the temporary copy in sync after changing migrations.

The three foundation migrations were applied to production through the Supabase migration API. Their repository filenames match the recorded production versions. Future hosted promotion should use a scoped `SUPABASE_ACCESS_TOKEN` and project-specific `SUPABASE_DB_PASSWORD` held in CI secrets; compare `migration list` and schema before `db push`. Never put a project password in a command argument or the repo. Validate each migration from zero and through upgrade locally before production.

## Ownership and roles

Supabase Auth owns `auth.users`, identities, refresh tokens, and sessions. The application profile is `app_private.profiles(id uuid references auth.users.id)`. Authorization uses the verified user UUID. Email and `raw_user_meta_data` are not authorization inputs. There is no product table in an exposed Data API schema. Local PostgREST has no exposed schema; disable the hosted Data API while the MVP uses server-side access only.

| Role | Auth tables | `app_private.profiles` | `runtime_private` / `vault_private` | DDL |
| --- | --- | --- | --- | --- |
| `anon`, `authenticated` | Supabase-managed Auth APIs only | None | None | None |
| `service_role` | Supabase-managed Auth administration | None | None | None |
| `gg_runtime` | No direct table access | `SELECT`, `INSERT`, `UPDATE` with UUID-scoped RLS | No access until later migrations grant specific objects | None |
| Migrator (`postgres` via CI) | Supabase-managed | Owner | Owner | Migration DDL |

The migration creates `gg_runtime` without a password. A separate random password was provisioned for production after the migration and saved only in Railway's `GG_RUNTIME_DATABASE_URL` server variable; `GG_DB_POOL_MAX=4` was also saved. The variable update skipped redeployment, so the current SQLite runtime was not switched over. Do not use the migrator URL for runtime requests. Later migrations must grant only the exact runtime/vault tables and operations needed by tasks 078 and 063. `gg_runtime` has no `BYPASSRLS`, no schema creation, and no `auth.users` read access. Backend code must verify the Auth session, then `SET LOCAL app.user_id` to its UUID in each profile transaction; an unset or different UUID sees no rows.

## Database connections

The production runtime uses the **shared Session pooler** over IPv4 at `aws-0-us-west-2.pooler.supabase.com:5432`, as shown in this project's Dashboard → Connect panel. Railway's `gg-runtime` currently has IPv6 egress disabled, while the direct Supabase host is IPv6-only. Its username is `gg_runtime.xmqpgubedtjirohntdwg`. The server keeps a bounded Psycopg pool (`max_size=4` by default, hard cap 8, `min_size=0`, five-second acquisition and connect timeouts), with prepared statements disabled. The runtime role has a 15-second statement timeout, five-second lock timeout, and 15-second idle-transaction timeout. `gg.runtime.postgres.RuntimePostgres` rejects the direct host, transaction pooler port 6543, other roles, and production URLs without `sslmode=verify-full`. The server package includes the public Supabase Root 2021 CA downloaded from this project's Database Settings; its SHA-256 fingerprint is `80:70:25:AD:50:D4:ED:21:9D:2C:9C:7D:29:9C:00:4F:82:4E:B0:0C:F7:F6:5A:FE:F6:07:D0:7B:72:E6:CA:FA`. Enable SSL enforcement in the Supabase dashboard after checking existing clients. The local CLI database does not offer TLS, so the integration test uses its direct loopback port 54322 with `sslmode=disable`.

Use `GG_RUNTIME_DATABASE_URL` only on the runtime server. Its password, the migrator password, service-role/secret API keys, and any future vault encryption key must remain in server-side secret stores. Never add them to `VITE_*`, browser storage, a checked-in `.env`, logs, or client bundles. A Supabase project URL and publishable key may be public if task 061 uses a browser client, but they confer no table access under the grants above.

| Variable or setting | Local | Production | Owner |
| --- | --- | --- | --- |
| Supabase URL and publishable key | `supabase status` | Project dashboard | Public configuration only if a browser client is introduced |
| `GG_RUNTIME_DATABASE_URL` | Loopback direct URL, temporary password in tests | Session pooler URL as `gg_runtime.xmqpgubedtjirohntdwg` at `aws-0-us-west-2.pooler.supabase.com:5432`, `sslmode=verify-full`; CA bundled with server | Runtime secret manager |
| `GG_DB_POOL_MAX` | Default 4 | 1–8 per runtime instance, sized to connection budget | Runtime server |
| `SUPABASE_ACCESS_TOKEN`, `SUPABASE_DB_PASSWORD` | Unused | Scoped CI token and migrator password | Deployment secret store |
| Google OAuth client ID/secret | Disabled | Supabase Auth provider configuration | Supabase project administrators |
| Session/cookie and vault encryption keys | Not yet used | Separate server secrets when tasks 061/063 add them | Server secret manager |

## Auth and Google callbacks

Configure the production Google OAuth client and secret in Supabase Auth for task 061. Google's authorized redirect URI points to `https://xmqpgubedtjirohntdwg.supabase.co/auth/v1/callback`; the Supabase allowed redirect URL points to the app's exact `https://<production-domain>/auth/callback`. Set the site URL to that HTTPS app origin. Local Auth uses `http://127.0.0.1:5173/auth/callback`; local Google OAuth remains disabled until task 061 exercises its PKCE callback. Google client secrets belong in Supabase provider configuration, never in Vite.

## Hosted readiness before opening traffic

1. Verify each migration version once, check the role matrix with read-only SQL, and run security and performance advisors. Do not create open policies to clear an advisor.
2. Run `PYTHONPATH=packages/gg-server uv run --no-editable python scripts/supabase_production_smoke.py` with the server-only `GG_RUNTIME_DATABASE_URL`. It checks authenticated Session pooler access, CA verification, the role timeout, denied Auth schema access, and profile isolation without writes or fixtures. Repeat from the actual production runtime host before task 078 cuts over.
3. Enable SSL enforcement, review Auth password protection, backups/retention, and monitor connection count before the runtime migration.

Production now records the three foundation migrations. Read-only checks confirmed the private schemas, limited login, UUID-scoped RLS, and role denials; the performance advisor has no findings. Revoking public execution of `public.rls_auto_enable()` cleared its security findings. The remaining Auth advisor warns that leaked-password protection is disabled; [Supabase lists that control as Pro-only](https://supabase.com/docs/guides/auth/password-security#password-strength-and-leaked-password-protection). Review Auth signup settings when task 061 configures Google-only sign-in. An authenticated read-only smoke from the developer host passed through the production Session pooler with `sslmode=verify-full`. Reachability from Railway and SSL enforcement remain rollout checks for task 078.
