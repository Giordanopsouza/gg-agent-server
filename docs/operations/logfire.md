# Logfire observability

`gg-runtime` exports production traces directly to Logfire. Each `gg-server` sandbox sends OTLP traces to an authenticated `gg-runtime` relay, so the Logfire write token remains in the control plane. Task state still comes from SQLite and durable task events.

## Production configuration

Configure the runtime with:

| Variable | Value |
| --- | --- |
| `GG_LOGFIRE_ENABLED` | `true` |
| `GG_LOGFIRE_ENVIRONMENT` | `production` |
| `GG_LOGFIRE_SAMPLE_RATE` | `1` initially |
| `GG_LOGFIRE_RELAY_URL` | Public runtime origin plus `/internal/logfire` |
| `LOGFIRE_TOKEN` | Write token for the Logfire project, in the runtime secret only |

The US project [giordano/agent-server](https://logfire-us.pydantic.dev/giordano/agent-server) was confirmed through the authenticated Logfire CLI. Configure its write token in the runtime secret before enabling production export. The relay URL must be reachable from Modal sandboxes. The runtime passes the relay URL, task ID, and task-scoped session key to each sandbox. The sandbox has no Logfire token. The relay accepts only `v1/traces`, verifies the task's session key against its SQLite record, and limits each request body to 1 MiB.

Set `GG_LOGFIRE_ENABLED=false` to disable instrumentation. A configured runtime requires `GG_LOGFIRE_RELAY_URL` before creating sandboxes. Restart both the runtime and sandbox image after changing instrumentation code or configuration. If Logfire export fails, the batch exporter drops telemetry without failing a task.

## Explore a task

Filter by `task_id` to see admission, dispatch, sandbox execution, Pi RPC/tool events, and SQLite query spans. Runtime-to-sandbox HTTP calls propagate trace context. Background spans may form separate traces correlated by `task_id`.

For example, in Logfire Explore:

```sql
SELECT start_timestamp, service_name, span_name, attributes
FROM records
WHERE attributes->>'task_id' = '<task UUID>'
ORDER BY start_timestamp
```

HTTP spans record method, route template, and status; health checks, task polling, and the relay endpoint are excluded. SQLite spans within an active request or task trace record operation and code location, without SQL text or bound values. Schema validation and connection setup queries are excluded. Pi telemetry records model, conversation ID, tool name, error flag, and duration when available. Raw request URLs, headers, bodies, prompts, answers, tool arguments/results, and exception messages are excluded from application spans. No alerts are configured in this rollout.

Review ingestion volume and retention after the initial full-sample production run before changing `GG_LOGFIRE_SAMPLE_RATE`.
