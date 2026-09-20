# Modal sandbox operations

Task sandboxes use the standard Modal Sandbox API (gVisor containers), not
nested Docker or the VM beta. The pinned control-plane SDK is `modal==1.5.5`.
The named runtime image is `gg-agent-server:2026-09-20-v1` and contains:

| Runtime | Pinned version |
|---|---:|
| Python | 3.12.11 |
| uv | 0.11.2 |
| Node.js | 22.23.1 |
| Pi coding agent | 0.83.0 |
| Git | 2.39.5 |
| GitHub CLI | 2.100.0 |

Build and publish it from the repository root:

```console
uv run --no-editable python -m gg.runtime.modal_image
```

## Quota and resource semantics

The Modal app (`gg-agent-sandboxes` by default) must already be deployed before
named sandboxes can be created. The workspace also needs quota for the selected
concurrency and for each sandbox's requested resources. Defaults pass
`cpu=(2, 2)` and `memory=(4096, 4096)` to Modal 1.5.5. In that SDK these tuples
mean `(request, hard limit)`: CPU is throttled at the limit and the memory
request/limit is expressed in MiB. Startup readiness is bounded at five minutes
and the provider-enforced absolute lifetime is 70 minutes.

## Pricing

Requests and limits describe scheduling and containment, not guaranteed cost
bounds. Modal bills actual resource usage under the workspace's current plan
and pricing. Check the workspace quota and current Modal pricing before choosing
capacity; do not infer a maximum bill from these resource tuples.

Connections use Modal Sandbox Connect Tokens over HTTPS/WSS and the agent
server's independent `X-API-Key`. Neither token is returned in task records.
Creation identity is durable before the provider call and sent both as a unique
sandbox name and tags, allowing a lost create response to be reconciled without
blindly creating another sandbox.

Run the opt-in live smoke after authenticating the Modal CLI and publishing the
image:

```console
GG_RUN_MODAL_TESTS=1 uv run --no-editable pytest \
  packages/gg-server/tests/test_modal_sandbox_live.py -m modal
```

The smoke creates one sandbox, authenticates to `/health`, reconnects from a
fresh lifecycle client, terminates it, and confirms provider termination.
