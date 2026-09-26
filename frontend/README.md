# Task web UI

Small React UI for the existing `gg.runtime` Task API. It submits tasks and polls
durable event copies using `after=<cursor>`. Polling is used because browser
WebSockets cannot send the runtime's required `X-API-Key` handshake header.

## Run locally

Start the control plane as described in the [root README](../README.md). Its
default URL is `http://127.0.0.1:8001`. Then:

```bash
cd frontend
npm ci
npm run dev
```

Open the Vite URL and save the value of `GG_RUNTIME_API_KEY` in the sidebar.
The key is stored in this browser's `localStorage` until you clear it. No
GitHub or model key is accepted by the UI. With the default setup, Vite proxies
`/tasks` to `http://127.0.0.1:8001`, so the browser stays on one origin.

## Configuration

- `VITE_DEV_API_PROXY`: development proxy target. Defaults to
  `http://127.0.0.1:8001`.
- `VITE_TASK_API_URL`: browser-visible Task API base URL, set at build time.
  Omit it when serving UI and API behind one origin with `/tasks` routed to
  the control plane. Set it to a full URL if the API is on a different origin.
- `GG_RUNTIME_CORS_ORIGINS`: comma-separated exact UI origins allowed by the
  runtime for cross-origin requests, for example
  `https://tasks.example.com,http://localhost:5173`. Configure this on the
  runtime when `VITE_TASK_API_URL` points to a different origin.

Build and verify:

```bash
npm test
npm run build
npm run preview
```

The build is static and can be served by any static host. Direct navigation
uses hash URLs (`#/tasks/<id>`), so no server fallback route is required.

The API owns task state and results. The UI shows the Task API's lifecycle
state (`queued`, `starting`, `running`, `finalizing`, `completed`, `failed`, or
`cancelled`) and uses `manifest.agent_outcome` for completed tasks when it is
available (`succeeded`, `no_changes`, and so on). The follow-up composer is
intentionally read-only in this version.
