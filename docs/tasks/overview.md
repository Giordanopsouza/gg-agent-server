# Plan: local server, Docker, fake runtime

Back-link: [task tracker](README.md). Architecture: [About the OpenHands agent-server](../architecture.md).

## Context

This repo is a learning clone of OpenHands agent-server. The goal is to feel the sandbox inversion by building it, not by reading it. OpenHands has one agent-server process and several launchers. We build that process once, then wrap it in Docker, then put a tiny HTTP provisioner in front of Docker.

## Scope

Included:

- Slice 1. An in-process conversation loop, then the same loop behind a local FastAPI server with file persistence and one WebSocket.
- Slice 2. A Docker image of that server plus a client launcher that `docker run`s it and talks HTTP.
- Slice 3. A fake runtime API that starts and stops those containers and returns `{url, session_api_key}`.

Excluded:

- Real Kubernetes, sysbox, or OpenHands Cloud.
- Leases, idle eviction, crash recovery, Fernet, profiles, deferred init.
- VSCode, VNC, git router, a second bash event channel, MCP, OpenAI gateway.
- A real LLM until the dummy agent can write `NOTES.md`. That work sits in [backlog/024-real-llm-loop.md](backlog/024-real-llm-loop.md).

## Constraints

- Python 3.12, uv workspace, two packages: `gg-sdk` and `gg-server`. `gg.sdk` must not import `gg.server`.
- Persistence is JSON files. No database.
- Dummy agent only. Scripted `write_file` actions, no model calls.
- Auth is one header, `X-Session-API-Key`. Bind `127.0.0.1` when no key is set.
- Isolation in slice 2 is the container, not a path jail.
- Each task is independently shippable and ends in a test or a demo command you can run.

## Alternatives

1. Start with Docker. Rejected. You would debug uvicorn inside a container before the loop exists.
2. One Python package. Rejected. The OpenHands lesson is the import DAG. Two packages are the smallest way to keep that lesson.
3. Real Kubernetes for slice 3. Rejected. Slice 3 exists to show that Cloud and K8s are provisioners. A fake runtime API teaches that. A cluster does not.

Chosen path: loop, then local server, then Docker, then fake runtime.

## Applicable skills

- **how** before changing an unfamiliar file.
- **model-the-domain** for conversation status and events.
- **type-system-discipline** for status as a sum type, not booleans.
- **boundary-discipline** for HTTP and env parsing.
- **sequence-verifiable-units** for one green task before the next.
- **prove-it-works** on the real surface: script, HTTP, Docker, then the fake API.
- **unslop** on every markdown edit. `/deslop` before commit.
- **laziness-protocol** if a task starts growing a fourth file. Split the task instead.

## Phases

Slice 1a is the old "slice 0". The loop has to exist before the server.

| Slice | Goal | Tasks |
|---|---|---|
| 1a In-process loop | A dummy agent writes `NOTES.md` with no HTTP | [001](done/001-repo-scaffolding.md) to [007](007-in-process-demo.md) |
| 1b Local server | Same loop over HTTP and WebSocket, reconnect works | [008](008-server-config.md) to [016](016-local-server-demo.md) |
| 2 Docker sandbox | Same server inside a container | [017](017-server-dockerfile.md) to [020](020-docker-sandbox-demo.md) |
| 3 Fake runtime | HTTP provisioner that starts that container | [021](021-runtime-control-api.md) to [023](023-runtime-api-demo.md) |

## Verification

Project-level, once the matching slice exists:

```bash
uv run pytest
uv run ruff check .
uv run python -m gg.sdk.demo.write_notes
uv run python -m gg.server --host 127.0.0.1 --port 8000
uv run python -m gg.sdk.demo.docker_notes
uv run python -m gg.sdk.demo.runtime_notes
```

No browser control skill applies. Surface is CLI, HTTP, and Docker. Flag: there is no `control-cli` wiring in this repo yet. Each demo task names the exact command and the file that must appear.

## Implementation guidance

Do not start 008 until 007 is green. Do not start 017 until 016 is green. Do not start 021 until 020 is green.

The how skill runs over `gg.sdk` before 008 wraps it, and over `gg.server` before 017 copies it into an image.

Interrogate only if someone proposes a database, a real K8s chart, or merging the two packages.

Keep a decision trail in each task `## Log`. This plan is large enough for that.

No PR skill until the user asks to publish.
