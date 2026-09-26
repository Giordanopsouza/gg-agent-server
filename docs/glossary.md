# Glossary

**Background task** — One long-running prompt with progress, evidence, and an outcome. It may optionally target a repository and produce a draft pull request.

**Capacity reservation** — A place in the ten-sandbox limit held while an environment is starting, active, being removed, or not yet confirmed absent.

**Finalization** — The phase after agent work when the platform preserves results, optionally publishes repository changes as a draft pull request, and releases the environment. New agent messages are no longer accepted.

**Retry** — A new background task linked to a terminal predecessor. It has its own environment and, for repository work, its own branch; existing remote changes are not undone.

**Task evidence** — Recorded events, check outcomes, revisions, artifacts, and pull-request references available for inspecting a task's result.

**Session** — Durable collaborative thread. It may receive many prompts and survive indefinitely.

**Run** — One execution attempt caused by a prompt. It is retryable and cancellable.

**Sandbox** — Disposable isolated execution resource assigned to a background task or run. Its lifetime ends after completion, failure, or cancellation.

**Event** — Append-only fact associated with a session and optionally a run.

**Artifact** — Durable output such as logs, patch, screenshots, test results, or plan.

**Delivery** — Branch, commit, PR, and CI state.

**Profile** — Data describing model, rules, skills, tools, image, verification commands, and sandbox policy.
