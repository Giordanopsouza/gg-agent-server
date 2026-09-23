---
status: accepted
---

# Remove the pre-Modal learning surfaces

The shipped path is the control plane in `gg.runtime`: it admits tasks into SQLite and dispatches them to Modal sandboxes. Inside each sandbox, `gg.server` still runs Pi through the conversation service and the task supervisor. The earlier learning path is not on that path and is deleted.

This supersedes two clauses in [ADR 0001](0001-modal-background-tasks.md): the requirement to preserve historical Docker demos, and the product default that tasks run configured repository bootstrap and check commands. Import boundaries stay as 0001 stated them. `gg.sdk` does not import `gg.server`. `gg.runtime` reaches the agent server only over HTTP.

## Removed

These modules had no caller on the Modal task path:

- `gg.sdk.tools`, the pre-Pi `WriteFileTool` registry. Pi supplies its own tools.
- `gg.sdk.repository_profiles`. The runtime does not load an allowlist or bootstrap and check commands. A repository task sends `owner/name` and `base_ref`.
- `gg.sdk.docker_workspace`, `gg.sdk.runtime_workspace`, and `gg.sdk.remote_conversation`. These started a local container and talked to it as a session.
- The control-plane session API: `POST /start`, `GET /sessions/{id}`, `POST /stop`, and `GG_RUNTIME_IMAGE`. Dispatch uses `GG_MODAL_IMAGE_NAME`.
- The learning demos `pi_notes`, `docker_pi_notes`, and `docker_pi_github_pr`, with their Makefile targets.

## Kept

The sandbox agent stays. `LocalWorkspace`, `LocalConversation`, `PiRpcAgent`, the conversation and event routes, and the task supervisor are how a dispatched task runs. The repository `Dockerfile` remains the Modal image. `RemoteWorkspace` stays because Modal sends `X-Session-API-Key` from that module.

## Trade-offs

Deleting the session API removes a local Docker fallback. A control-plane process can no longer `docker run` an agent server beside Modal. Reproducing a task locally means running `gg.runtime` with dispatch enabled against Modal, which is the path covered by the single-host demo. Historical task notes under `docs/tasks/done/` stay as a record of how those surfaces were built.

## Approval

Accepted by the user on 2026-09-22, after a local control plane with `GG_TASK_DISPATCH_ENABLED=true` completed a general task (`agent_outcome=succeeded`). Delivered on the branch that removes the surfaces.
