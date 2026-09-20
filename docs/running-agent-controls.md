# Running-agent messages and cancellation

The agent server supports idempotent steering and cooperative cancellation for
an active conversation. The implementation follows the RPC contract shipped in
the sandbox image's pinned Pi coding agent **0.83.0**. The authoritative
protocol reference is the versioned
[Pi RPC documentation](https://github.com/earendil-works/pi/blob/v0.83.0/packages/coding-agent/docs/rpc.md),
not whichever `pi` executable happens to be installed on the host.

## Message receipts

Send a client-generated, conversation-scoped ID while the conversation is
`running`:

```http
POST /api/conversations/{conversation_id}/messages
Content-Type: application/json

{"id":"client-message-42","content":"Check the failing test first."}
```

The receipt is persisted before the `steer` command is written to Pi. Reusing
the ID with identical content returns the existing receipt without forwarding
again; reusing it with different content returns HTTP 409. Receipts can also be
read at `GET /api/conversations/{conversation_id}/messages/{message_id}`.

Receipt states deliberately describe knowledge, not model behavior:

| Status | Meaning |
|---|---|
| `accepted` | Durably stored locally, before the Pi acknowledgement is known. |
| `delivered_to_pi` | Pi acknowledged that `steer` was queued for its next safe boundary. |
| `failed` | Pi explicitly rejected the steering command. |
| `unknown` | The acknowledgement was lost; Pi may or may not have queued it. |

`delivered_to_pi` does **not** mean the model saw, understood, or acted on the
message. Pi 0.83.0 delivers steering after the current assistant turn finishes
its tool calls and before the next model call. An `unknown` message must not be
automatically replayed, because replay could produce a duplicate effect.

The equivalent WebSocket frame is:

```json
{"type":"steer","id":"client-message-42","content":"Check the failing test first."}
```

It receives a direct `message_receipt` frame. The accepted user message is also
present in the durable event stream.

## Cancellation

`POST /api/conversations/{conversation_id}/cancel`, or WebSocket frame
`{"type":"cancel"}`, stops message acceptance atomically, sends Pi's correlated
`abort` command, closes its stdin, and waits the configured grace period. The
server starts Pi in a separate process session and signals the entire process
group with TERM and then KILL when necessary. A successful cancellation response
therefore means no Pi tool descendant from that run remains able to write.

The grace period is persisted in `agent.cancel_grace_seconds`; Pi command
acknowledgements use `agent.command_ack_timeout_seconds`. Both default to five
seconds. Cancellation is idempotent after it begins or completes. Once Pi emits
`agent_settled`, the same serialized boundary stops accepting new messages, so a
racing request is either durably accepted for the run or rejected with HTTP 409.

## Verification

Offline tests use a long-lived fake RPC subprocess to cover HTTP, WebSocket,
steer acknowledgement, lost acknowledgement, settlement races, abort, and
process-tree termination. The opt-in smoke runs the same controls against Pi
0.83.0 inside `gg-agent-server:dev`:

```console
GG_RUN_DOCKER_PI_CONTROL_TESTS=1 uv run --no-editable pytest \
  packages/gg-server/tests/test_running_conversation_controls.py -m "docker and pi"
```

Build the image first and configure `OPENROUTER_API_KEY`; this smoke makes a paid
model request.
