# Backend

The backend is the control plane. Its Python import package remains `gg.runtime`.
The API admits tasks and owns durable state; the runtime schedules and
supervises sandbox work. It communicates with `gg.server` only over HTTP and
WebSocket contracts, never through Python imports. Shared contracts live in
`gg.sdk`. Keep routes thin and initialize state through FastAPI lifespan hooks.
