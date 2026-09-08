# Docker Pi demo

The Docker Pi demo drives a real Pi agent through `RemoteConversation` inside
an isolated `gg-agent-server` container. It forwards the host OpenRouter key by
environment name only, asks Pi to write `PI_NOTES.md`, proves the file with
`docker exec`, and always stops the container. No host workspace is mounted.

Build the image, export the key, then run:

```bash
docker build -t gg-agent-server:dev .
export OPENROUTER_API_KEY=...
uv run python -m gg.sdk.demo.docker_pi_notes
```

Pass `--image` to use a tag other than `gg-agent-server:dev`. The working
directory inside the container is `/workspace/project`.

The dummy Docker demo remains the offline checkpoint:

```bash
uv run python -m gg.sdk.demo.docker_notes
```

The paid live smoke test is opt-in. It skips if Docker, the image, or the key
is unavailable:

```bash
GG_RUN_DOCKER_PI_TESTS=1 uv run --no-editable pytest -m "docker and pi"
```
