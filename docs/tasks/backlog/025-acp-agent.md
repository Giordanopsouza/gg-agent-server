---
id: 025-acp-agent
feature: acp
status: pending
depends_on: [020-docker-sandbox-demo]
---

# ACP agent (bring your own agent)

## Migration preflight

- **Target end-state:** `ACPAgent` in `gg.sdk` spawns an ACP-compatible subprocess (Claude Code, Codex, Gemini CLI) inside the sandbox `working_dir`. `ConversationService` can start a conversation with `agent_kind: acp` instead of the dummy or native LLM loop.
- **Temporary legacy bridges:** none.
- **Forbidden legacy dependencies:** baking ACP subprocess management into `gg.server`. Keep spawn, session, and relay logic in `gg.sdk`.
- **Bridge removal task:** n/a.
- **Boundary enforcement:** `gg.sdk` must not import `gg.server`. Docker image pre-installs ACP CLIs; server only selects agent settings from the create request.

## Scope

Add Agent Client Protocol support so users can run third-party coding agents (Claude Code via `claude-agent-acp`, Codex, Gemini) inside the gg sandbox instead of on their laptop. Mirror the upstream `ACPAgent` pattern from `software-agent-sdk`.

## Acceptance criteria

- [ ] `ACPAgentSettings` with `acp_server` (`claude-code`, `codex`, `gemini-cli`, `custom`) and `acp_model` lives in `gg.sdk`.
- [ ] `ACPAgent` spawns the resolved command as a subprocess with `cwd=workspace.working_dir` and relays `session/prompt` over JSON-RPC stdio.
- [ ] ACP tool-call events are appended to the conversation event log and stream on the WebSocket.
- [ ] With no API key for the chosen provider, the conversation fails with a clear error; the dummy agent path is unchanged.
- [ ] Docker image (`017`) pre-installs pinned `claude-agent-acp` / `codex-acp` / `gemini --acp` binaries on `PATH`.
- [ ] `uv run python -m gg.sdk.demo.acp_notes` (or equivalent) starts a container, runs Claude Code (or a stub ACP echo server in tests), and shows output under `/workspace`.

## Out of scope

- Native LLM loop (`024-real-llm-loop`). Pick one agent path per conversation, not both.
- ACP remote HTTP transport (stdio only for v1).
- Full provider registry UI, credential Fernet, or every upstream `ACPAgent` edge case.
- Running ACP on the client's laptop while proxying fs/terminal to a remote sandbox (OpenHands runs the subprocess inside the sandbox).

## References

- Upstream: `software-agent-sdk/openhands-sdk/openhands/sdk/agent/acp_agent.py`
- Upstream: `software-agent-sdk/openhands-sdk/openhands/sdk/settings/acp_providers.py`
- Protocol: https://agentclientprotocol.com/protocol/overview
- Claude Code adapter: https://github.com/agentclientprotocol/claude-agent-acp

## Log

### [PA] 2026-08-22 15:45 — Grooming

Parked after slice 2. Enables the product pitch: bring your Claude Code / Codex / Gemini runtime; execution happens in our sandbox. Depends on Docker sandbox so the ACP subprocess runs inside the container, not on the host.
