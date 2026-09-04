# Local Pi demo

The local Pi demo runs a real Pi RPC subprocess through `LocalConversation`; it
does not start the gg server or Docker. Install the pinned CLI and provide an
OpenRouter key:

```bash
npm install -g --ignore-scripts @earendil-works/pi-coding-agent@0.83.0
export OPENROUTER_API_KEY=...
uv run python -m gg.sdk.demo.pi_notes
```

By default the command creates a temporary workspace and leaves it on disk. Its
output includes that path, the contents of `PI_NOTES.md`, the final assistant
text, and a persisted-event summary. To use a directory you choose:

```bash
uv run python -m gg.sdk.demo.pi_notes --workspace /path/to/workspace
```

The paid live smoke test is opt-in. It skips if Pi or the key is unavailable:

```bash
GG_RUN_PI_TESTS=1 uv run --no-editable pytest -m pi
```
