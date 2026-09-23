# gg-sdk

Client-side Python package for domain models, local conversations, the task client, and agent backends. Preserve its independence from `gg.server`; use frozen Pydantic models for shared state, async I/O at remote boundaries, and tests beside this package. See the root [`AGENTS.md`](../../AGENTS.md) for repository-wide workflow and conventions; run `make -C packages/gg-sdk help` for component commands.
