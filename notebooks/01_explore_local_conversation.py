"""Hands-on tour of Slice 1a — build the loop one object at a time.

Run cell-by-cell in Cursor/VS Code, or execute the whole file:

    uv run python notebooks/01_explore_local_conversation.py

Or use the Jupyter notebook version:

    uv run jupyter notebook notebooks/01_explore_local_conversation.ipynb

Artifacts land in ``notebooks/scratch/`` (gitignored). Open that folder
in the file tree while you step through the cells.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path


try:
    from gg.sdk import (
        EventLog,
        LocalConversation,
        LocalWorkspace,
        load_base_state,
        load_meta,
    )
except ModuleNotFoundError:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages" / "gg-sdk"))
    from gg.sdk import (
        EventLog,
        LocalConversation,
        LocalWorkspace,
        load_base_state,
        load_meta,
    )

# %%
# --- 0. Pick a sandbox directory -------------------------------------------
# Everything we create stays under ``scratch/`` so you can delete it anytime.

ROOT = Path(__file__).resolve().parent / "scratch" / "explore-1"
WORKSPACE_DIR = ROOT / "workspace"
CONVERSATION_DIR = ROOT / "conversation"

if ROOT.exists():
    shutil.rmtree(ROOT)

WORKSPACE_DIR.mkdir(parents=True)
CONVERSATION_DIR.mkdir(parents=True)

print("workspace:   ", WORKSPACE_DIR)
print("conversation:", CONVERSATION_DIR)

# %%
# --- 1. LocalWorkspace — the agent's disk ----------------------------------
# The workspace is just a folder on your machine. Tools read/write here.

workspace = LocalWorkspace(working_dir=WORKSPACE_DIR)

workspace.write_file("hello.txt", "written before the conversation starts\n")
print("workspace files:", list(WORKSPACE_DIR.iterdir()))
print(workspace.read_file("hello.txt").decode())

# %%
# --- 2. LocalConversation — wires workspace + event log ------------------
# On init, the conversation writes meta.json and base_state.json immediately.

conversation = LocalConversation(
    conversation_dir=CONVERSATION_DIR,
    workspace=workspace,
)

print("id:    ", conversation.id)
print("status:", conversation.status)
print()
print("meta.json:", (CONVERSATION_DIR / "meta.json").read_text())
print("base_state.json:", (CONVERSATION_DIR / "base_state.json").read_text())

# %%
# --- 3. send_message — record intent, do not run the agent yet -------------
# Status stays IDLE. Only a MESSAGE event is appended.

conversation.send_message("my first hands-on message")

print("status after send_message:", conversation.status)
events = EventLog(CONVERSATION_DIR).list()
print("event count:", len(events))
print("latest event:", events[-1].kind, events[-1].payload)

# %%
# --- 4. run — dummy agent plans, tool executes, events accumulate ----------
# This is the same internal loop the HTTP server will call later.

conversation.run()

print("status after run:", conversation.status)
print()
print("NOTES.md:\n---")
print((WORKSPACE_DIR / "NOTES.md").read_text())
print("---")

# %%
# --- 5. Read the full event timeline ---------------------------------------
# Each step of the loop left a JSON file under conversation/events/.

events = EventLog(CONVERSATION_DIR).list()
for event in events:
    print(f"{event.seq:02d} {event.kind:12} {event.payload}")

# %%
# --- 6. Reload from disk (simulates server restart) ------------------------
# New Python objects, same folders — persistence is just JSON files.

reloaded_meta = load_meta(CONVERSATION_DIR)
reloaded_state = load_base_state(CONVERSATION_DIR)
reloaded_events = EventLog(CONVERSATION_DIR).list()

print("meta status:", reloaded_meta.status)
print("base_state:", reloaded_state.model_dump())
print("events on disk:", len(reloaded_events))

# %%
# --- 7. Peek at raw files (optional) ---------------------------------------

def tree(path: Path, prefix: str = "") -> None:
    """Pretty-print a directory tree."""
    entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name))
    for i, entry in enumerate(entries):
        connector = "└── " if i == len(entries) - 1 else "├── "
        print(prefix + connector + entry.name)
        if entry.is_dir():
            extension = "    " if i == len(entries) - 1 else "│   "
            tree(entry, prefix + extension)


print(f"\n{ROOT.name}/")
tree(ROOT)

print("\nSample event file:")
event_file = next((CONVERSATION_DIR / "events").glob("event-*.json"))
print(event_file.name)
print(json.dumps(json.loads(event_file.read_text()), indent=2))
