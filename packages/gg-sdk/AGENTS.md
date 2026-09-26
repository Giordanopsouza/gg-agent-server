# gg-sdk

Client-side Python package for shared Pydantic HTTP contracts, the task client,
and the `gg-task` CLI. It must be independently importable and never import
`gg.server` or `gg.runtime`. Sandbox-local Pi, workspace, and conversation
execution live in `sandboxes/gg/server/agent`.
