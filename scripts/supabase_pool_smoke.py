"""Verify the bounded runtime pool through local direct Postgres."""

import json
import os
import secrets
import subprocess
from pathlib import Path
from urllib.parse import quote

from gg.runtime.postgres import RuntimePostgres


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "node_modules/.bin/supabase"
WORKDIR = os.environ.get("SUPABASE_LOCAL_WORKDIR", str(ROOT))


def cli(*args: str) -> str:
    return subprocess.run(
        [str(CLI), "--workdir", WORKDIR, *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def main() -> None:
    status_text = cli("status", "-o", "json")
    status = json.loads(status_text[status_text.index("{") :])
    if status["API_URL"] != "http://127.0.0.1:54321":
        raise SystemExit("Pool smoke only runs against local Supabase")

    password = secrets.token_urlsafe(30)
    cli("db", "query", "--local", f"alter role gg_runtime password '{password}'")
    try:
        username = quote("gg_runtime", safe="")
        encoded_password = quote(password, safe="")
        os.environ["GG_RUNTIME_DATABASE_URL"] = (
            f"postgresql://{username}:{encoded_password}@127.0.0.1:54322/postgres"
            "?sslmode=disable"
        )
        config = RuntimePostgres.from_env()
        with config.pool() as pool, pool.connection() as connection:
            role, timeout = connection.execute(
                "select current_user, current_setting('statement_timeout')"
            ).fetchone()
            if role != "gg_runtime" or timeout != "15s":
                raise AssertionError(
                    f"Unexpected runtime role or timeout: {role}, {timeout}"
                )
            connection.execute("select count(*) from app_private.profiles").fetchone()
    finally:
        cli("db", "query", "--local", "alter role gg_runtime password null")
        os.environ.pop("GG_RUNTIME_DATABASE_URL", None)
    print("Local bounded pool, direct runtime login and timeouts passed")


if __name__ == "__main__":
    main()
