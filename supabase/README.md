# Supabase local environment

Supabase owns Auth and supplies the local/hosted Postgres service. The SQL files
in `migrations/` are the frozen history that produced application schema
version 7 before Alembic was introduced; do not add new application migrations
there.

New changes to `app_private`, `runtime_private`, and `vault_private` are created
under `backend/alembic/versions/` and reflected in
`backend/gg/runtime/db_models.py`. The root `supabase-local-reset` target runs
the historical Supabase migrations, then makes Alembic validate and adopt that
schema.
