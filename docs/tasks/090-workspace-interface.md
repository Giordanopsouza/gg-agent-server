---
id: 090-workspace-interface
feature: mvp-web
status: done
depends_on: []
---

# Workspace interface based on the supplied reference

## Scope
Replace the dense task creation form with a centered composer on a white canvas,
a pale workspace sidebar, and compact model, repository, and branch controls.
Move credentials and GitHub setup to Settings. Add a Tasks overview, searchable
history, collapsible workspace groups, and a mobile navigation drawer. Preserve
session handling, per-account drafts, submission contracts, and task activity.
Use system fonts and inline SVG icons without adding dependencies.

## Validation
- `npm test`: 15 frontend tests and the production server suite pass; includes
  the TypeScript check and production build.
- New interaction checks cover history search and collapse, navigation with
  draft preservation, selected model/repository/branch keyboard submission,
  credential gating, and mobile navigation.
- Root QA passed in order: `make format-fix`, `make lint-fix`,
  `make format-check`, `make lint-check`, `make pre-commit`, `make unit-tests`.
  Both unit runs: 221 passed, 92 skipped, 2 deselected.
- User explicitly waived the live runtime task demo and requested a PR.
  No background task was submitted. Browser visual verification and real
  sandbox execution remain unverified.

## Log
### [SWE] 2026-10-06 PDT — Implementation and checks
Implemented the reference layout in the dedicated 090-workspace-interface
worktree and verified the frontend interactions and required repository QA.
