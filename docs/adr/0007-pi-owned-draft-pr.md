---
status: accepted
---

# Pi publishes the draft pull request

For a user-owned repository task, Pi commits, pushes, and creates or updates the draft pull request with the task's installation token. The control plane records the intended repository, branch, base, and task marker before that work, then verifies the pull request on GitHub by repository, head, base, marker, and canonical URL. A URL written in the conversation is not publication. The host does not open a second pull request when Pi's publication is missing, uncertain, or already done.

The installation token can write. A prompt that says not to merge does not technically prevent a merge; repository protections are what limit that. This flow creates draft pull requests and leaves merge to a person on GitHub. Check results stay `passed`, `failed`, or `not_run`. A completed run is not treated as green CI.

Operator tasks that have no owner still use the host publisher and still keep ambient `GH_TOKEN` out of Pi. This replaces the clause in [ADR 0001](0001-modal-background-tasks.md) that kept GitHub credentials out of Pi for every task.
