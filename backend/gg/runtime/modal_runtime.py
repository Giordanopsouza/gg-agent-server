"""Single SQLite writer on Modal. Deploy only with this module's recreate entrypoint.

python -m gg.runtime.modal_runtime --environment ENV
Initialize the environment's gg-runtime-state snapshot explicitly first.
"""

import argparse
import os
import tempfile
import threading
from pathlib import Path

import modal
import uvicorn

from gg.runtime.app import create_app
from gg.runtime.config import load_settings
from gg.runtime.db_cli import restore
from gg.runtime.runtime_image import runtime_image


app = modal.App("gg-runtime")
volume = modal.Volume.from_name("gg-runtime-state", create_if_missing=False)
secret = modal.Secret.from_name("gg-runtime-config")
SNAPSHOT = Path("/state/runtime.snapshot")


def restored_app(snapshot: Path, local: Path, commit):
    """Validate and restore before wiring or opening the listening socket."""
    restore(snapshot, local)
    os.environ["GG_RUNTIME_DB_PATH"] = str(local)
    os.environ["GG_RUNTIME_SNAPSHOT_PATH"] = str(snapshot)
    return create_app(load_settings(), snapshot_commit=commit, internal_proxy=True)


@app.server(
    image=runtime_image() if modal.is_local() else None,
    volumes={"/state": volume},
    secrets=[secret],
    min_containers=1,
    max_containers=1,
    buffer_containers=0,
    port=8000,
    unauthenticated=True,
    startup_timeout=120,
    exit_grace_period=20,
)
class Runtime:
    @modal.enter()
    async def start(self):
        await volume.reload.aio()
        self.local = tempfile.TemporaryDirectory(prefix="gg-runtime-")
        application = restored_app(
            SNAPSHOT, Path(self.local.name) / "runtime.db", volume.commit.aio
        )
        self.server = uvicorn.Server(
            uvicorn.Config(
                application,
                host="0.0.0.0",
                port=8000,
                workers=1,
                proxy_headers=False,
                timeout_graceful_shutdown=15,
            )
        )
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()

    @modal.exit()
    def stop(self):
        self.server.should_exit = True
        self.thread.join(timeout=25)
        if self.thread.is_alive():
            raise RuntimeError("runtime did not drain before shutdown")
        self.local.cleanup()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True)
    args = parser.parse_args()
    with modal.enable_output():
        app.deploy(environment_name=args.environment, strategy="recreate")
        print(Runtime.get_url())


if __name__ == "__main__":
    main()
