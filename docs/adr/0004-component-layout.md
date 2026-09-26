---
status: accepted
---

# Separate control plane, frontend, sandbox, and Python client code

The repository groups code by where it runs. `backend/` contains the Task API and its runtime scheduler in one control plane deployment; `frontend/` calls that API directly over HTTP; `sandboxes/` contains the per-task image, agent server, and Pi execution. `packages/gg-sdk/` contains shared Pydantic contracts, the Python Task API client, and its CLI. Backend and sandbox use the shared contracts, and the backend reaches the sandbox only through HTTP/WebSocket.

The previous `gg-server` distribution packaged both control-plane and sandbox modules, while `gg-sdk` also packaged sandbox-local execution. Separate `gg-backend` and `gg-sandbox` distributions make image contents and ownership clear. The import names `gg.runtime` and `gg.server` remain stable to avoid changing the service entry points and HTTP contract during the move.

This adds two Python distributions and requires separate package, image, and frontend build checks. The React client maintains its own TypeScript API types; generating types from the HTTP schema can be considered if those contracts grow. Existing tracked `workspace/` data is preserved, while new runtime data is ignored by Git.
