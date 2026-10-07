---
id: 089-scheduler-recovery
feature: mvp-web
status: done
depends_on: []
---

# Recover scheduler cycles and report dispatch health

## Problem
Production task 14 remains queued without a reservation or sandbox. Runtime logs
show SQLAlchemy pool timeouts. An exception escaping a scheduler cycle ends the
background loop while dispatch and readiness still report healthy configuration.
The failure mechanism was reproduced locally; the exact production loop exception
cannot be inspected through the existing endpoints.

## Change
Log failed cycles and retry on the configured polling interval. Report whether
the loop is running, its latest cycle timestamp, the error type, and storage
admission blocking. Return not-ready while the loop is stopped or a cycle fails.
Do not expose database error details through the operator status endpoints.

## Validation
- Root QA sequence passed in order: format-fix, lint-fix, format-check,
  lint-check, pre-commit, unit-tests. Available suite: 221 passed, 92 skipped,
  2 deselected. Existing missing test_support was supplied from /tmp, not added
  to the repository.
- With local Postgres enabled, all 20 scheduler, recovery, and production
  operation tests passed. The broader suite had 310 passes and three failures:
  history archival signature and retention cadence also fail on the previous
  revision; the conversation appearance test passed when rerun in isolation.
- User requested production validation instead of the local end-to-end demo.
  Local processes started for preparation were stopped; no local demo task was
  submitted.
- Published backend commit `b88aa67` to the existing Railway production runtime:
  deployment `73838e64-4b16-4721-ae7e-57c7491c9f07` succeeded. Task 14 left the
  queue without resubmission and started sandbox `sb-yZTSrleFk86UoxZrLFFTyF`.
- Running supervision exposed additional pool pressure at four connections.
  Production Postgres had 22 connections out of 60 available. Set the existing
  `GG_DB_POOL_MAX` variable to 8, within the application's supported bound;
  deployment `cdac2030-fdae-4851-81d8-4b7ecdaed63c` succeeded. Task execution
  continued across the runtime restart.
- Through `https://gg-web-production.up.railway.app`, `/health` and `/ready`
  returned 200, dispatch reported a live scheduler with no error or blocked
  admission, and the browser loaded the authenticated task detail. No new pool
  timeouts, scheduler-cycle failures, or 503 responses appeared in the checked
  logs between startup at 23:54 UTC and final verification at 23:56 UTC.
- Task `7bc0be0f-b09c-4a9f-92c8-4b5aac4300ea` produced 40 archived events,
  including its final response and finished event. It reached `idle`, with
  `agent_outcome=succeeded` and `evidence_complete=true`. The complete patch
  changes the display/title name to `Giorfano` in `lib/content.ts`,
  `app/blog/[slug]/page.tsx`, and `app/page.tsx`. The workspace stays available
  for follow-up messages; the agent did not commit or publish the site changes.
- Website build validation remains unproven: `next` was absent from the
  checkout, and fallback `npx` attempts failed. The manifest reports
  `check_outcome=not_run`. Queue recovery, real sandbox execution, prompt
  fulfillment, and durable result archival were verified in production.
