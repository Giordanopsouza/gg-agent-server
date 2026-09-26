"""Exercise local Supabase Auth and its Postgres profile FK.

Set SUPABASE_LOCAL_WORKDIR when Docker Desktop cannot mount the repository.
The --upgrade path resets only the named local Docker project.
"""

import argparse
import json
import os
import secrets
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

import psycopg
from psycopg import sql


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "node_modules/.bin/supabase"


def cli(*args: str) -> str:
    workdir = Path(os.environ.get("SUPABASE_LOCAL_WORKDIR", ROOT))
    result = subprocess.run(
        [str(CLI), "--workdir", str(workdir), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def auth_request(
    url: str, key: str, path: str, payload: dict | None = None, token: str | None = None
) -> dict:
    headers = {"apikey": key, "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(payload).encode() if payload is not None else None
    with urlopen(
        Request(f"{url}/auth/v1/{path}", data=data, headers=headers), timeout=10
    ) as response:
        return json.load(response)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upgrade", action="store_true")
    args = parser.parse_args()

    if args.upgrade:
        if os.environ.get("SUPABASE_RESET_TARGET") != "gg-agent-server":
            raise SystemExit(
                "Set SUPABASE_RESET_TARGET=gg-agent-server for local upgrade test"
            )
        cli("db", "reset", "--local", "--no-seed", "--last", "1")

    status_text = cli("status", "-o", "json")
    status = json.loads(status_text[status_text.index("{") :])
    url = status["API_URL"]
    parsed = urlsplit(url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise SystemExit("Auth smoke only runs against loopback local Supabase")
    if urlsplit(status["DB_URL"]).hostname not in {"127.0.0.1", "localhost"}:
        raise SystemExit("Database URL must be local")

    email = f"foundation-{uuid.uuid4().hex}@example.test"
    signup = auth_request(
        url,
        status["PUBLISHABLE_KEY"],
        "signup",
        {"email": email, "password": secrets.token_urlsafe(24)},
    )
    user_id = str(uuid.UUID(signup["user"]["id"]))
    token = signup["access_token"]
    if args.upgrade:
        cli("migration", "up", "--local")

    user = auth_request(url, status["PUBLISHABLE_KEY"], "user", token=token)
    if user["id"] != user_id:
        raise AssertionError("Auth user UUID changed across request or migration")

    with psycopg.connect(status["DB_URL"], autocommit=True) as connection:
        password = secrets.token_urlsafe(30)
        try:
            connection.execute(
                "insert into app_private.profiles (id) values (%s)", (user_id,)
            )
            assert connection.execute(
                "select count(*) from auth.users where id = %s", (user_id,)
            ).fetchone() == (1,)
            connection.execute(
                sql.SQL("alter role gg_runtime password {}").format(
                    sql.Literal(password)
                )
            )
            runtime_url = (
                "postgresql://gg_runtime:"
                f"{quote(password, safe='')}@127.0.0.1:54322/postgres?sslmode=disable"
            )
            with psycopg.connect(runtime_url, autocommit=True) as runtime:
                with runtime.transaction():
                    assert runtime.execute(
                        "select count(*) from app_private.profiles"
                    ).fetchone() == (0,)
                    runtime.execute(
                        "select set_config('app.user_id', %s, true)", (user_id,)
                    )
                    assert runtime.execute(
                        "select count(*) from app_private.profiles"
                    ).fetchone() == (1,)
                    runtime.execute(
                        "select set_config('app.user_id', %s, true)",
                        (str(uuid.uuid4()),),
                    )
                    assert runtime.execute(
                        "select count(*) from app_private.profiles"
                    ).fetchone() == (0,)
        finally:
            connection.execute("alter role gg_runtime password null")
            connection.execute("delete from auth.users where id = %s", (user_id,))
    print("Local Auth, profile FK, UUID isolation, and cleanup passed")


if __name__ == "__main__":
    try:
        main()
    except (KeyError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"Local Supabase integration failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
