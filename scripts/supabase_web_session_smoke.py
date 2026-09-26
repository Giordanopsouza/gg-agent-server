"""Prove profile creation and Auth revocation against disposable local Supabase."""

import base64
import json
import os
import secrets
import subprocess
import uuid
from pathlib import Path
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

import psycopg
from psycopg import sql

from gg.runtime.postgres import RuntimePostgres
from gg.runtime.web_sessions import PostgresWebSessions


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "node_modules/.bin/supabase"


def main() -> None:
    result = subprocess.run(
        [str(CLI), "status", "-o", "json"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    status = json.loads(result[result.index("{") :])
    url = status["API_URL"]
    if urlsplit(url).hostname not in {"127.0.0.1", "localhost"}:
        raise SystemExit("This smoke runs only against local Supabase")
    email = f"web-session-{uuid.uuid4().hex}@example.test"
    signup = Request(
        f"{url}/auth/v1/signup",
        data=json.dumps(
            {"email": email, "password": secrets.token_urlsafe(24)}
        ).encode(),
        headers={"apikey": status["PUBLISHABLE_KEY"], "Content-Type": "application/json"},
    )
    with urlopen(signup, timeout=10) as response:
        tokens = json.load(response)
    user_id = tokens["user"]["id"]
    encoded_claims = tokens["access_token"].split(".")[1]
    claims = json.loads(base64.urlsafe_b64decode(encoded_claims + "=="))
    session_id = claims["session_id"]

    with psycopg.connect(status["DB_URL"], autocommit=True) as admin:
        password = secrets.token_urlsafe(30)
        try:
            admin.execute(
                sql.SQL("alter role gg_runtime password {}").format(
                    sql.Literal(password)
                )
            )
            os.environ["GG_RUNTIME_DATABASE_URL"] = (
                f"postgresql://gg_runtime:{quote(password, safe='')}"
                "@127.0.0.1:54322/postgres?sslmode=disable"
            )
            with RuntimePostgres.from_env().pool() as pool:
                sessions = PostgresWebSessions(pool)
                assert sessions.active(user_id, session_id)
                assert not sessions.ensure_profile(user_id, str(uuid.uuid4()))
                assert sessions.ensure_profile(user_id, session_id)
                assert admin.execute(
                    "select count(*) from app_private.profiles where id = %s",
                    (user_id,),
                ).fetchone() == (1,)
                logout = Request(
                    f"{url}/auth/v1/logout?scope=local",
                    data=b"{}",
                    headers={
                        "apikey": status["PUBLISHABLE_KEY"],
                        "Authorization": f"Bearer {tokens['access_token']}",
                        "Content-Type": "application/json",
                    },
                )
                with urlopen(logout, timeout=10):
                    pass
                assert not sessions.active(user_id, session_id)
        finally:
            os.environ.pop("GG_RUNTIME_DATABASE_URL", None)
            admin.execute("alter role gg_runtime password null")
            admin.execute("delete from auth.users where id = %s", (user_id,))
    print("Local profile creation and revoked-session rejection passed")


if __name__ == "__main__":
    main()
