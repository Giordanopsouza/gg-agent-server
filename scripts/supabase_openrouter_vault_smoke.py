"""Exercise the credential vault against disposable local Supabase Postgres."""

import json
import os
import secrets
import subprocess
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import psycopg
from cryptography.fernet import Fernet
from psycopg import sql
from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url

from gg.runtime.openrouter_vault import PostgresOpenRouterVault


ROOT = Path(__file__).resolve().parents[1]
CLI = Path(os.environ.get("SUPABASE_CLI", ROOT / "node_modules/.bin/supabase"))


def runtime_engine(db_url: str):
    engine = create_engine(make_url(db_url).set(drivername="postgresql+psycopg"))

    @event.listens_for(engine, "connect")
    def set_runtime_role(dbapi_connection, _connection_record) -> None:
        dbapi_connection.execute("set role gg_runtime")

    return engine


def main() -> None:
    output = subprocess.run(
        [
            str(CLI),
            "--workdir",
            os.environ.get("SUPABASE_LOCAL_WORKDIR", str(ROOT)),
            "status",
            "-o",
            "json",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    status = json.loads(output[output.index("{") :])
    api_url, db_url = status["API_URL"], status["DB_URL"]
    if any(
        urlsplit(url).hostname not in {"localhost", "127.0.0.1"}
        for url in (api_url, db_url)
    ):
        raise SystemExit("vault smoke only runs against local Supabase")
    users = []
    for _ in range(2):
        request = Request(
            f"{api_url}/auth/v1/signup",
            data=json.dumps(
                {
                    "email": f"vault-{uuid.uuid4().hex}@example.test",
                    "password": secrets.token_urlsafe(24),
                }
            ).encode(),
            headers={
                "apikey": status["PUBLISHABLE_KEY"],
                "Content-Type": "application/json",
            },
        )
        with urlopen(request, timeout=10) as response:
            users.append(json.load(response)["user"]["id"])
    secret = "sk-or-v1-" + secrets.token_urlsafe(30)
    engine = None
    with psycopg.connect(db_url, autocommit=True) as admin:
        already_member = admin.execute(
            "select pg_has_role('postgres', 'gg_runtime', 'member')"
        ).fetchone()[0]
        can_set_role = admin.execute(
            "select pg_has_role('postgres', 'gg_runtime', 'set')"
        ).fetchone()[0]
        try:
            if not can_set_role:
                admin.execute("grant gg_runtime to postgres with set true")
            for user_id in users:
                admin.execute(
                    "insert into app_private.profiles (id) values (%s)", (user_id,)
                )
            engine = runtime_engine(db_url)
            vault = PostgresOpenRouterVault(engine, Fernet.generate_key().decode())
            assert vault.status(users[0])["configured"] is False
            assert vault.replace(users[0], secret)["version"] == 1
            assert vault.status(users[1])["configured"] is False
            assert vault.replace(users[1], "sk-or-v1-other-user-1234")["version"] == 1
            assert vault.status(users[0])["mask"] == f"••••{secret[-4:]}"
            assert vault.replace(users[0], secret + "2")["version"] == 2
            rows = admin.execute(
                "select owner_id, ciphertext "
                "from vault_private.openrouter_credentials "
                "where owner_id = any(%s)",
                (users,),
            ).fetchall()
            assert len(rows) == 2
            assert all(secret.encode() not in bytes(row[1]) for row in rows)
            vault.remove(users[0])
            assert vault.status(users[0])["configured"] is False
            assert vault.status(users[1])["configured"] is True
            for role in ("anon", "authenticated", "service_role"):
                with admin.transaction():
                    admin.execute(
                        sql.SQL("set local role {}").format(sql.Identifier(role))
                    )
                    try:
                        with admin.transaction():
                            admin.execute(
                                "select * from vault_private.openrouter_credentials"
                            )
                    except psycopg.errors.InsufficientPrivilege:
                        pass
                    else:
                        raise AssertionError(f"{role} could read the vault")
            request = Request(
                f"{api_url}/rest/v1/openrouter_credentials?select=*",
                headers={
                    "apikey": status["PUBLISHABLE_KEY"],
                    "Accept-Profile": "vault_private",
                },
            )
            try:
                with urlopen(request, timeout=10) as response:
                    raise AssertionError(f"Data API exposed vault: {response.status}")
            except HTTPError as error:
                assert error.code in (401, 403, 404, 406)
        finally:
            if engine is not None:
                engine.dispose()
            if not can_set_role:
                if already_member:
                    admin.execute("grant gg_runtime to postgres with set false")
                else:
                    admin.execute("revoke gg_runtime from postgres")
            admin.execute("delete from auth.users where id = any(%s)", (users,))
    print(
        "Local vault ciphertext, isolation, replacement, removal, and API denial passed"
    )


if __name__ == "__main__":
    main()
