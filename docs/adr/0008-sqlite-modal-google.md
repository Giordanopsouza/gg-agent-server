---
status: accepted
---

# Keep the runtime's durable state in SQLite snapshots on Modal

The control plane runs as one Modal Server with one Uvicorn worker and one
SQLite writer. Its active database stays on local disk with WAL, full sync and
foreign keys; a single checkpoint coordinator copies a complete, validated
snapshot to the Modal Volume and commits it. A mutation returns success only
after the snapshot containing its revision is confirmed. Background activity
is checkpointed periodically. Startup restores a validated snapshot, then
reconciles external work before admitting new tasks. Initialization is explicit;
a missing or invalid snapshot after that fails closed.

This chooses a smaller single-writer system over the former shared Postgres
ledger. Modal deployment uses `recreate` so old and new runtime servers do not
write concurrently. The Volume stores snapshots, not the live WAL database,
and is not a multi-writer database. State from the former Postgres deployment
is not imported; users reconnect their credentials.

Google OpenID Connect supplies external identity. The verified Google `sub`
maps to a local UUID; email is display data and never an ownership key. Local
opaque sessions, GitHub account links and installation IDs, sandbox/run IDs,
message delivery keys and publication IDs retain the identities needed to
reconcile effects after a restart. Only session-token hashes and encrypted
personal credentials enter SQLite; encryption keys and provider secrets stay
outside snapshots in the Modal Secret. The React UI and API share the public
Modal origin and communicate with sandboxes through HTTP/WebSocket contracts.

This supersedes [ADR 0005](0005-runtime-postgres-ledger.md) and
[ADR 0006](0006-sqlalchemy-alembic.md). Their original reasoning remains as
history of the earlier architecture.
