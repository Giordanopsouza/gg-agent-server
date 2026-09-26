# Web authentication (task 061)

Supabase Auth owns Google identities and refresh sessions. The runtime handles the
browser redirect and keeps the Supabase access and refresh tokens inside an
encrypted HttpOnly cookie. The operator `X-API-Key` remains separate: a web
session cannot call `/tasks` until task 062 adds owner authorization.

## Configuration

Set these on the runtime host, never in the Vite bundle:

| Variable | Purpose |
|---|---|
| `GG_SUPABASE_URL` | Project URL, such as `https://<ref>.supabase.co` |
| `GG_SUPABASE_PUBLISHABLE_KEY` | Project publishable key used by the runtime for Auth requests |
| `GG_WEB_COOKIE_KEY` | Persistent Fernet key; generate once with `Fernet.generate_key()` and store outside Git |
| `GG_WEB_ORIGIN` | Exact browser origin, without a trailing slash |
| `GG_WEB_COOKIE_SECURE` | Defaults to `true`; `false` is accepted only for loopback development |

Configure Google under Supabase Authentication > Providers, and allow
`<GG_WEB_ORIGIN>/auth/google/callback` as a Supabase redirect URL. Google uses
the Supabase OAuth callback URL shown in that provider's settings. Serve the
frontend and `/auth` on the same HTTPS origin in staging and production.
The runtime verifies access JWTs with the project's public JWKS. The selected
project currently advertises an ES256 signing key; a project using legacy
HS256 must rotate to an asymmetric signing key before this integration works.

## HTTP contract

- `GET /auth/google/start?return_to=/...` redirects to Supabase Auth with PKCE.
  The return path must be relative to this site.
- `GET /auth/google/callback` exchanges the one-use code and sets `gg_session`.
- `GET /auth/session` returns `{ "user": { "id": "<uuid>", "email": "..." } }`.
  Missing or expired sessions return 401.
- `POST /auth/logout` needs an exact `Origin` header. It requests local sign-out
  from Supabase, then clears the cookie.

For a real opt-in test, configure a Google OAuth client in the Supabase project,
open `/auth/google/start`, complete Google consent, check `/auth/session`, reload,
then send `POST /auth/logout` with the web origin and confirm `/auth/session`
returns 401. Also try cancelling consent and a second callback with the same
code. Record the project/environment and result without copying tokens or
secrets into logs. The deterministic HTTP tests use a controlled Auth server;
they do not prove Google consent or deployed callback settings.

Supabase Auth revokes refresh tokens on sign-out; an already issued JWT can
remain valid until its expiry. Task 077's private Postgres access is required
for checking `auth.sessions` on sensitive operations. Until task 062 adds owner
checks, all task routes remain operator only.
