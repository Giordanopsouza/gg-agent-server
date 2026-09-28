# Personal OpenRouter credential vault

The browser sends a key only in the JSON body of `PUT /auth/openrouter-credential`.
`GET` returns `{configured, mask, version}` and `DELETE` clears the credential.
All routes require the verified Supabase Auth cookie and an active Auth session;
`PUT` and `DELETE` also require the exact configured `Origin`. Responses do not
contain the key and are marked `Cache-Control: no-store`. The browser must not
put a key in a URL, localStorage, a task prompt, or a public task payload.

The backend calls [OpenRouter's current-key endpoint](https://openrouter.ai/docs/api/api-reference/api-keys/get-current-api-key)
using the Authorization header before saving. HTTP 401/403 means invalid key;
402/429 means a provider limit; network and other provider failures mean
unavailable. None changes a previously saved key. A successful check confirms
only that the key was accepted at that moment. It does not reserve credit or
guarantee any particular model will be available for a later execution.

Set `GG_OPENROUTER_VAULT_KEY` to a dedicated Fernet key in the runtime secret
manager, separate from `GG_WEB_COOKIE_KEY`. Generate it with
`Fernet.generate_key()` and keep it out of Git, Postgres, Supabase Auth, and
the Vite bundle. Postgres stores ciphertext, key version, a short mask, and a
monotonic credential version in `vault_private.openrouter_credentials`.
Only `gg_runtime` has table grants, and RLS scopes each transaction to the
verified owner's UUID. `anon`, `authenticated`, and `service_role` have no
schema or table access. The schema is absent from the Data API exposure list.

Replacement atomically advances the credential version. Removal clears the
ciphertext and mask and advances the version, leaving a tombstone so a later
replacement cannot reuse an old reference. New executions should resolve the
current owner's credential and version immediately before starting; they
should fail closed after removal. Task 064 wires that dispatch path. Existing
executions may already have received the previous key and continue using it;
removal here cannot revoke an OpenRouter key. To stop those executions, cancel
them and revoke the key at OpenRouter.

For encryption-key rotation, pause new credential writes and dispatch, decrypt
each ciphertext with the old server key, re-encrypt with the new server key,
increment `key_version`, deploy the new key, then resume. Keep the old key
available until all rows and any rollback window have been handled. Do not
store either encryption key in the database. A lost key makes saved credentials
unrecoverable; users must replace them.

Verification: run `make supabase-integration-tests` against disposable local
Supabase, then `PYTHONPATH=backend uv run --no-editable python
scripts/supabase_openrouter_vault_smoke.py`. The smoke signs up two local users,
checks ciphertext and owner isolation, and confirms direct role and Data API
denials. It cleans up the synthetic users and temporary local role grant.
