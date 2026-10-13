# Task 133: WPP account authentication

Bind one dedicated bearer token to an existing account using GG_WPP_API_TOKEN
and GG_WPP_OWNER_ID. No schema or frontend changes. Validate the pair, UUID,
existing owner and separation from the operator key at startup. Keep task and
socket ownership checks. SDK uses GG_TASK_API_TOKEN with no operator fallback.
Definitive missing-credential startup errors must terminate the sandbox and
release the reservation; transient errors retry without fetching absent executions.
Verify auth/isolation/socket/CLI and failure cleanup, then root Makefile QA.
Published proof requires configured WPP credentials and deployment of this code.

## Verification boundary

A real `gg-task --json submit` subprocess called an isolated loopback HTTP
runtime with an explicitly initialized SQLite database/checkpoint. It saved the
configured account ID despite a stale operator key. Dispatch was disabled for
this authentication demo. Automated integration tests cover the same CLI path,
owner isolation, event sockets, personal credential dispatch (existing suite),
permanent startup failure cleanup and transient errors without execution polling.

Full platform proof remains pending: the local stack on ports 8001/5173 is not
running with an authenticated Google session, and the published runtime has not
received the new WPP settings/code. No production Secret, deployment, active task
or WPP repository was changed. Deploy/configure and update the WPP SDK before
claiming an end-to-end agent response/PR and released reservation in Modal.
