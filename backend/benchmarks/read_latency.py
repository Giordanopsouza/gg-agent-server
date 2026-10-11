"""Compare HEAD's read path with this worktree using isolated SQLite state.

Run from the root: uv run --no-editable python backend/benchmarks/read_latency.py
The 50 ms commit delay is synthetic, not a Modal/network measurement.
"""

import asyncio
import json
import subprocess
import sys
import tempfile
import types
from pathlib import Path
from time import perf_counter
from uuid import UUID

import httpx

from gg.runtime.app import create_app
from gg.runtime.checkpoints import CheckpointCoordinator
from gg.runtime.config import RuntimeSettings
from gg.runtime.google_auth import GoogleAuth
from gg.runtime.ledger import TaskLedger
from gg.runtime.local_sessions import LocalSessions
from gg.runtime.sqlite_db import SQLiteDB, initialize


BASELINE = sys.argv[1] if len(sys.argv) > 1 else "HEAD"


def baseline(name):
    source = subprocess.check_output(
        ["git", "show", f"{BASELINE}:backend/gg/runtime/{name}.py"], text=True
    )
    module = types.ModuleType(f"baseline_{name}")
    sys.modules[module.__name__] = module
    exec(compile(source, f"{BASELINE}:{name}.py", "exec"), module.__dict__)
    return module


async def measure(label, coordinator_class, sessions_class, app_factory):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        initialize(root / "db")
        with SQLiteDB(root / "db") as db:
            commits = 0

            async def commit():
                nonlocal commits
                commits += 1
                await asyncio.sleep(0.05)

            checkpoints = coordinator_class(db, root / "snapshot", commit)
            sessions = sessions_class(db, checkpoints)
            token = await sessions.create("reader", "reader@example.com")
            owner = UUID((await sessions.user(token))["id"])
            ledger = TaskLedger(db, checkpoints)
            task, _ = ledger.submit(
                idempotency_key="bench",
                repository=None,
                prompt="hello",
                base_ref=None,
                retry_of=None,
                owner_id=owner,
            )
            settings = RuntimeSettings(api_key="local", web_origin="http://127.0.0.1")
            auth = GoogleAuth(settings, sessions)
            app = app_factory(
                settings,
                web_auth=auth,
                task_ledger=ledger,
                web_sessions=sessions,
                checkpoints=checkpoints,
            )
            app.state.recovering = False
            await checkpoints.ensure_durable(db.revision)
            output = {"version": label, "commit_delay_ms": 50}

            def dirty():
                with db.write() as tx:
                    tx.connection.execute(
                        "UPDATE tasks SET updated_at = updated_at WHERE id = ?",
                        (str(task.id),),
                    )
                return tx.revision

            async def timed(name, action):
                start, before = perf_counter(), commits
                await action()
                output[name] = {
                    "ms": round((perf_counter() - start) * 1000, 2),
                    "commits": commits - before,
                }

            dirty()
            await timed(
                "four_session_reads",
                lambda: asyncio.gather(*(sessions.user(token) for _ in range(4))),
            )
            revision = dirty()
            await timed(
                "four_revision_waiters",
                lambda: asyncio.gather(
                    *(checkpoints.ensure_durable(revision) for _ in range(4))
                ),
            )
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://127.0.0.1",
                cookies={"gg_session": token},
            ) as client:

                async def requests(path, count, status):
                    responses = await asyncio.gather(
                        *(client.get(path) for _ in range(count))
                    )
                    assert all(response.status_code == status for response in responses)

                dirty()
                await timed("four_get_tasks", lambda: requests("/tasks", 4, 200))
                dirty()
                client.cookies.set("gg_session", "invalid")
                await timed(
                    "invalid_cookie_get_tasks", lambda: requests("/tasks", 1, 401)
                )
                client.cookies.set("gg_session", token)
                await checkpoints.ensure_durable(db.revision)
                await timed(
                    "task_data_clean",
                    lambda: asyncio.gather(
                        *(
                            requests(path, 1, 200)
                            for path in (
                                f"/tasks/{task.id}",
                                f"/tasks/{task.id}/events",
                                f"/tasks/{task.id}/result",
                            )
                        )
                    ),
                )
            await auth.close()
            print(json.dumps(output, indent=2))


async def main():
    await measure(
        BASELINE,
        baseline("checkpoints").CheckpointCoordinator,
        baseline("local_sessions").LocalSessions,
        baseline("app").create_app,
    )
    await measure("worktree", CheckpointCoordinator, LocalSessions, create_app)


if __name__ == "__main__":
    asyncio.run(main())
