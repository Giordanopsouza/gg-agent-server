---
id: 088-task-latency
feature: mvp-web
status: in-progress
depends_on: []
---

# Reduce history and task-detail latency

## Scope
Return agent outcomes with the task list, render independently arriving detail data, reuse unchanged results, cache public signing keys and the Auth HTTP client, offload blocking database access from async runtime code, allow pooled reads alongside the serialized writer, and throttle retention to once per minute.

## Acceptance criteria
- [x] History uses one request per refresh and does not fetch individual results.
- [x] Task detail renders before events/results finish; unchanged results are reused.
- [x] Signing keys/client are reused while live user/session checks remain enforced.
- [x] Slow scheduler database calls do not block the event loop.
- [x] Corrected list and HTTP contract work against production with read-only connections.
- [ ] Publish and measure the authenticated browser flow on the current production deployment.
- [ ] Complete durable runtime regression tests and a real dispatched task.

## Validation
- Frontend: 10 tests passed; TypeScript and production bundle build passed.
- Focused latency regressions: 6 passed, 3 skipped (durable ledger fixtures need an isolated database).
- Available unit suite: 217 passed, 92 skipped, 2 deselected. The deleted `test_support` module was recovered under `/tmp` solely for this run; no production database URL was supplied to the suite.
- Root QA commands were attempted in the required order. Format/lint/pre-commit are blocked by pre-existing missing `tests/`, `scripts/`, and `test_support/` paths referenced by the Makefile. Changed-source format/lint passed.
- Production: read-only connection to the existing west-coast session pooler; schema validated; list returned 13 tasks and compact outcomes. Reads completed while the writer lock was held. The shared SQLAlchemy engine returned compatible rows.
- Production-backed HTTP check: ASGI transport, no lifespan/dispatch/maintenance, `GET /tasks` returned 200 with the new summary field in 560 ms. This is not a deployed HTTP measurement.
- Existing deployed operator endpoint at `https://gg-web-production.up.railway.app/tasks`: warm samples approximately 234–345 ms; initial connections varied. Operator requests bypass Google authentication and do not prove browser latency improvement.
- No production data or infrastructure configuration was modified, and no deployment was performed.

## Out of scope
Region migration, database schema changes, caching user/session authorization, and running destructive test fixtures against production.

## Log
### [SWE] 2026-10-06 America/Los_Angeles — implementation and production read validation
Created dedicated worktree `088-task-latency`. User directed database validation to production. Used read-only connections and disabled lifespan for the HTTP contract check. The deployed frontend/backend split differs from the main checkout; preserve it when preparing a deployment. Local credentials failed for the existing runtime role; do not change them as part of this task.
