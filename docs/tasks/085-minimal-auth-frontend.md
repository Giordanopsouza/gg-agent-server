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

Run frontend tests and `npm run build:runtime`, verify the FastAPI root and asset routes, then exercise the published UI. A real GitHub OAuth walkthrough needs a registered GitHub App and its credentials.
