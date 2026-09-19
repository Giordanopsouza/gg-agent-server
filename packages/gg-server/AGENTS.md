# gg-server

FastAPI package containing the remote conversation service (`gg.server`) and Docker-backed runtime control plane (`gg.runtime`). Keep app creation side-effect free, initialize state through lifespan hooks, parse configuration at the boundary, and keep routes thin over typed services. See the root [`AGENTS.md`](../../AGENTS.md) for repository-wide workflow and conventions; run `make -C packages/gg-server help` for component commands.
