---
id: 089-scheduler-recovery
feature: mvp-web
status: in-progress
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
  Local processes started for preparation were stopped. Pending: publish the
  backend and verify activity, sandbox execution, and result of production task 14.
