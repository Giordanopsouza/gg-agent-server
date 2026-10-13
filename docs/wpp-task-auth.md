# Tasks from the WPP agent

The runtime binds one dedicated bearer credential to an existing Google account.
No frontend changes or new database migration are needed.

Configure both values in the Modal `gg-runtime-config` Secret:

```dotenv
GG_WPP_API_TOKEN=<random-secret>
GG_WPP_OWNER_ID=<existing-local_users-id>
```

Generate the secret with `secrets.token_urlsafe(32)`. Keep it distinct from
`GG_RUNTIME_API_KEY`. The runtime refuses an incomplete pair, invalid UUID,
invalid token or an owner absent from its initialized SQLite snapshot.
Find the account ID in the authenticated browser's `GET /auth/session` response
(`user.id`); it is the gg account ID, not the Google subject or GitHub ID.
Update the Secret preserving its other values, then use the existing Modal
operations deployment/rollover protocol. Existing containers do not reload settings.

Install the updated SDK in the WPP repo and set:

```dotenv
GG_TASK_API_URL=<published-runtime-origin>
GG_TASK_API_TOKEN=<same-random-secret>
```

The packaged CLI is `gg-task`; a WPP wrapper named `gg` must use this updated SDK.
`gg-task submit` sends `Authorization: Bearer ...` for HTTP and event subscriptions.
The token takes precedence over a stale `GG_RUNTIME_API_KEY`; an empty or invalid
bearer never falls back to operator access. Do not put the token in the URL,
task payload, browser storage or logs. Requests with both authentication headers
are rejected.

The runtime sets the owner from configuration. Normal owner isolation, repository
authorization and personal OpenRouter credential dispatch apply. Tasks appear in
that account's frontend history. The token cannot access operator-only routes
or readiness/backup. Cookie authentication remains unchanged. Configure GitHub
and OpenRouter through the existing Settings screen before submitting work.

Rotate or remove the configured token and roll over the runtime to revoke it.
Existing submitted tasks retain their owner; changing the binding does not repair
old ownerless tasks. This integration represents the configured account, so its
WhatsApp caller authorization belongs to the WPP application.

Definitive missing-credential errors at execution start mark the task failed,
terminate its sandbox and release capacity only after termination is confirmed.
Transient start errors retain the reservation and retry the idempotent start
without polling an unacknowledged execution. The existing execution deadline
bounds retries.
