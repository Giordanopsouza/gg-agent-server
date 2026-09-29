---
id: 085-minimal-auth-frontend
feature: mvp-web
status: in-progress
depends_on: [061-google-login-and-sessions, 062-task-ownership-and-idempotency, 063-personal-openrouter-credentials, 064-user-model-and-credential-dispatch, 065-github-account-and-app-connection, 066-authorized-repositories-and-task-tokens]
---

# Minimal authenticated task frontend

## Scope

Replace the operator-key UI with a browser-session UI for trying the 061–066 flows: Google login, OpenRouter credential, GitHub account connection, authorized repository and branch selection, model selection, and task submission and observation. Bundle the UI into the runtime for same-origin cookies in production.

## Validation

Frontend tests, `npm run build:runtime`, the FastAPI root and asset routes, and the backend unit suite passed. The published Railway UI completed Google login and GitHub OAuth, then listed the connected account's authorized repositories and branches. The production `/health` endpoint returned HTTP 200, and `/webhooks/github` rejected an unsigned payload with HTTP 401.

Task submission and result observation still need a user-provided OpenRouter key for the signed-in account. The GitHub App is currently private to its owner's account; making it available to other users is a separate product rollout decision.
