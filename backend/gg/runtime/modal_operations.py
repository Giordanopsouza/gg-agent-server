"""Modal state operations. All supported commands share one named sandbox lease.

Offline operations restore a Volume snapshot into private local SQLite, never
open a database on the Volume. Only init creates a missing Volume. Production
operators must use these commands rather than raw deploy/rollover commands.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

import httpx
import modal

from gg.runtime.checkpoints import publish_snapshot, validate_snapshot
from gg.runtime.db_cli import migrate, restore
from gg.runtime.runtime_image import runtime_image, runtime_version
from gg.runtime.sqlite_db import SQLiteDB, initialize


def modal_cli(environment: str, *arguments: str):
    result = subprocess.run(
        [sys.executable, "-m", "modal", *arguments, "--env", environment],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def require_stopped(environment: str):
    apps = json.loads(modal_cli(environment, "app", "list", "--json"))
    if any(
        row["description"] == "gg-runtime"
        and (row["state"] != "stopped" or int(row["tasks"]) != 0)
        for row in apps
    ):
        raise RuntimeError(
            "stop the runtime and wait for all containers before changing state"
        )


@contextmanager
def operation_lease(environment: str):
    # Modal enforces uniqueness of running sandbox names within this stable App.
    # Hold this lease for deploy/rollover too, preventing supported commands from
    # starting a server while an offline operation is touching the snapshot.
    owner = modal.App.lookup(
        "gg-runtime-operations", environment_name=environment, create_if_missing=True
    )
    sandbox = modal.Sandbox.create(
        "sleep",
        "1800",
        app=owner,
        name="state-writer",
        image=runtime_image(),
        timeout=1800,
    )
    try:
        yield sandbox
    finally:
        sandbox.terminate(wait=True)


def offline_state(command: str, snapshot: Path, source: Path | None = None) -> int:
    """Called only in the isolated container after the controller proves stop."""
    with tempfile.TemporaryDirectory(prefix="gg-state-operation-") as directory:
        local = Path(directory) / "runtime.db"
        if command == "init":
            if snapshot.exists():
                raise FileExistsError("Volume already initialized")
            initialize(local)
        else:
            restore(
                source if command == "restore" else snapshot,
                local,
                allow_older=command == "migrate",
            )
            # Keep a closed previous snapshot before replacement.
            if snapshot.exists():
                validate_snapshot(snapshot, allow_older=command == "migrate")
                shutil.copyfile(snapshot, snapshot.with_suffix(".previous"))
        if command == "migrate":
            return migrate(local, snapshot)
        with SQLiteDB(local) as database:
            return publish_snapshot(database, snapshot)


def remote_state(command: str, environment: str, source: bytes | None = None) -> int:
    """A Modal Function has mount-scoped credentials for explicit Volume.commit."""
    volume = modal.Volume.from_name("gg-runtime-state", environment_name=environment)
    volume.reload()
    with tempfile.TemporaryDirectory(prefix="gg-restore-source-") as directory:
        source_path = Path(directory) / "restore.snapshot"
        if source is not None:
            source_path.write_bytes(source)
        revision = offline_state(
            command,
            Path("/state/runtime.snapshot"),
            source_path if source is not None else None,
        )
        volume.commit()
        return revision


def verify(url: str, *, expected_version: str | None = None, timeout: float = 180):
    key = os.environ["GG_RUNTIME_API_KEY"]
    deadline = time.monotonic() + timeout
    required_revision = None
    while True:
        try:
            with httpx.Client(
                base_url=url, headers={"X-API-Key": key}, timeout=10
            ) as client:
                health = client.get("/health")
                ready = client.get("/ready")
                health.raise_for_status()
                ready.raise_for_status()
                body = ready.json()
                if health.json()["status"] != "ok" or body["status"] != "ready":
                    raise ValueError("runtime not ready")
                if expected_version and body["version"] != expected_version:
                    raise ValueError("unexpected deployed version")
                if required_revision is None:
                    required_revision = body["revision"]
                if body["confirmed_revision"] < required_revision:
                    raise ValueError("revision not yet committed")
                return body
        except (httpx.HTTPError, ValueError, KeyError):
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    "health/ready/version/revision verification timed out"
                ) from None
            time.sleep(2)


def backup(url: str, destination: Path) -> int:
    if destination.exists():
        raise FileExistsError(destination)
    with httpx.Client(timeout=120) as client:
        response = client.post(
            url.rstrip("/") + "/ops/backup",
            headers={"X-API-Key": os.environ["GG_RUNTIME_API_KEY"]},
        )
        response.raise_for_status()
    # Validate before publishing the download, and refuse to replace any backup.
    with tempfile.TemporaryDirectory(dir=destination.parent) as directory:
        temporary = Path(directory) / "backup"
        temporary.write_bytes(response.content)
        revision = validate_snapshot(temporary)
        if revision != int(response.headers["X-Runtime-Revision"]):
            raise ValueError("backup revision mismatch")
        temporary.chmod(0o600)
        os.link(temporary, destination)
    return revision


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            "init",
            "migrate",
            "restore",
            "backup",
            "deploy",
            "rollover",
            "stop",
            "verify",
        ),
    )
    parser.add_argument("--environment", required=True)
    parser.add_argument("--url", help="deployed runtime URL (backup/rollover/verify)")
    parser.add_argument(
        "--snapshot", type=Path, help="local backup output or restore input"
    )
    args = parser.parse_args(argv)
    if args.command in {"backup", "rollover", "verify"} and not args.url:
        parser.error("--url is required")
    if args.command in {"backup", "restore"} and not args.snapshot:
        parser.error("--snapshot is required")
    if args.command in {"deploy", "rollover", "verify", "backup"} and not os.getenv(
        "GG_RUNTIME_API_KEY"
    ):
        parser.error(
            "GG_RUNTIME_API_KEY is required for authenticated verification/backup"
        )
    if args.command == "verify":
        print(json.dumps(verify(args.url), sort_keys=True))
        return
    with (
        modal.enable_output(),
        operation_lease(
            args.environment,
        ),
    ):
        if args.command in {"init", "migrate", "restore"}:
            require_stopped(args.environment)
            source = None
            if args.command == "restore":
                validate_snapshot(args.snapshot)
                source = args.snapshot.read_bytes()
            volume = modal.Volume.from_name(
                "gg-runtime-state",
                environment_name=args.environment,
                create_if_missing=args.command == "init",
            )
            command_app = modal.App("gg-runtime-state-command")
            command = command_app.function(
                image=runtime_image(),
                volumes={"/state": volume},
                max_containers=1,
                timeout=300,
            )(remote_state)
            with command_app.run(environment_name=args.environment):
                revision = command.remote(args.command, args.environment, source)
            print(f"{args.command}: revision={revision}")
        elif args.command == "stop":
            modal_cli(args.environment, "app", "stop", "gg-runtime", "--yes")
            for _ in range(60):
                try:
                    require_stopped(args.environment)
                    break
                except RuntimeError:
                    time.sleep(1)
            else:
                raise RuntimeError("runtime did not stop")
            print("runtime stopped; no containers")
        elif args.command == "backup":
            print(f"backup: revision={backup(args.url, args.snapshot)}")
        else:
            if args.command == "deploy":
                from gg.runtime.modal_runtime import Runtime, app

                app.deploy(environment_name=args.environment, strategy="recreate")
                url = Runtime.get_url()
                expected = runtime_version()
            else:
                expected = verify(args.url)["version"]
                modal_cli(
                    args.environment,
                    "app",
                    "rollover",
                    "gg-runtime",
                    "--strategy",
                    "recreate",
                )
                url = args.url
            report = verify(url, expected_version=expected)
            print(json.dumps({"url": url, **report}, sort_keys=True))
            print(modal_cli(args.environment, "app", "history", "gg-runtime", "--json"))


if __name__ == "__main__":
    main()
