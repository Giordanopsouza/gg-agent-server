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
| `LOGFIRE_TOKEN` | Project API key with Send telemetry permission, or a write token, in the runtime secret only |

The US project [giordano/agent-server](https://logfire-us.pydantic.dev/giordano/agent-server) was confirmed through the authenticated Logfire CLI. The production relay URL is `https://giordanowrk-sqlite-111-proof--gg-runtime-runtime.us-east.modal.direct/internal/logfire`, discovered through `modal.Server.from_name(...).get_url()` and verified through `/health`. The relay URL must be reachable from Modal sandboxes. The runtime passes the relay URL, task ID, and task-scoped session key to each sandbox. The sandbox has no Logfire token. The relay accepts only `v1/traces`, verifies the task's session key against its SQLite record, and limits each request body to 1 MiB.

Set `GG_LOGFIRE_ENABLED=false` to disable instrumentation. A configured runtime requires `GG_LOGFIRE_RELAY_URL` before creating sandboxes. Restart both the runtime and sandbox image after changing instrumentation code or configuration. If Logfire export fails, the batch exporter drops telemetry without failing a task.

## Explore a task

Filter by `task_id` to see admission, dispatch, sandbox execution, Pi execution summaries, slow/failed tool events, and slow/failed SQLite queries. Runtime-to-sandbox HTTP calls propagate trace context. Background spans may form separate traces correlated by `task_id`.

For example, in Logfire Explore:

```sql
SELECT start_timestamp, service_name, span_name, attributes
FROM records
WHERE attributes->>'task_id' = '<task UUID>'
ORDER BY start_timestamp
```

HTTP spans record method, route template, and status. Successful health checks, task/status/event polling, and relay requests below one second emit no HTTP record. Their HTTP errors, exceptions, and responses taking at least one second emit one sanitized diagnostic with elapsed time. Sandbox filters cover `/api` routes and older unprefixed routes. FastAPI/ASGI automatic scopes are suppressed at configuration so dependency, endpoint, serialization, and duplicate HTTP spans cannot bypass this policy.

SQLite queries emit no span per statement. Queries taking at least 100 ms emit `sqlite query slow`; failures emit `sqlite query failed`, including outside an active task span. These records contain operation, code location, elapsed time, and error type only. Schema validation and connection setup queries remain excluded. No SQL text or bound values are exported.

Pi retains the `pi RPC run` span with `tool_count`, `tool_error_count`, and cumulative `tool_duration_ms`. Individual tool records are kept for failures, calls taking at least one second, or missing start timing. Fast successful tools emit no individual telemetry; durable conversation action/observation events are unchanged. Task lifecycle records and configured sampling are unchanged. Raw request URLs, headers, bodies, prompts, answers, tool arguments/results, and exception messages are excluded from application spans. No alerts are configured in this rollout.

Review ingestion volume and retention after the initial full-sample production run before changing `GG_LOGFIRE_SAMPLE_RATE`.


## Verify the noise cut

Rebuild and restart the runtime and sandbox image to apply this policy. Existing
sandboxes keep their old instrumentation until replaced. Historical records are
not removed. Do not reduce the global sample rate to compensate for old images.

Compare a fresh time window by `service_name`, `span_name`, and `otel_scope_name`.
There should be no `sqlite query` spans, `fastapi.*` spans, or successful fast
polling/relay HTTP spans. A real task must still show admission, creation,
execution phases, Pi run and archival. HTTP/SQLite/tool failures and slow calls
must remain visible. Removing noise does not add missing queue or PR milestones.

Verification on 2026-10-17 used the `verification-136` environment in the US
`giordano/agent-server` project. Trace `01a14b923fe23f8600ef87033584ae3b`
contains one verification parent plus five operational records: HTTP 503, slow
HTTP 200, normal action HTTP, failed SQL, and slow SQL. One hundred successful
polling requests and one hundred fast SQLite queries emitted no individual
records. This verifies export and filtering, not deployment or a Google-authenticated
frontend task. The local sandbox `make run` also returned HTTP 200 with
`{"status":"ok"}` from port 8000. The local runtime/frontend on ports 8001/5173
were not running with an initialized snapshot and Google session, so that full
platform acceptance boundary remains untested.
