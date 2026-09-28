"""Run runtime tests in a disposable schema on local Supabase Postgres."""

from __future__ import annotations

import os
import secrets
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote, urlsplit

import psycopg
from psycopg import sql


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase/migrations/20260927000000_runtime_ledger.sql"
DEFAULT_ADMIN_URL = (
    "postgresql://postgres:postgres@127.0.0.1:54322/postgres?sslmode=disable"
)


def main() -> int:
    admin_url = os.getenv("GG_LOCAL_ADMIN_DATABASE_URL", DEFAULT_ADMIN_URL)
    if urlsplit(admin_url).hostname not in {"127.0.0.1", "localhost"}:
        raise SystemExit("Runtime Postgres tests require a local admin database")

    schema = f"runtime_test_{secrets.token_hex(6)}"
    password = secrets.token_urlsafe(30)
    with psycopg.connect(admin_url, autocommit=True) as admin:
        previous = admin.execute(
            "SELECT rolpassword FROM pg_authid WHERE rolname = 'gg_runtime'"
        ).fetchone()
        if previous is None:
            raise SystemExit("Local gg_runtime role is missing")
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            admin.execute(MIGRATION.read_text().replace("runtime_private", schema))
            admin.execute(
                sql.SQL("ALTER ROLE gg_runtime PASSWORD {}").format(
                    sql.Literal(password)
                )
            )
            env = os.environ.copy()
            env.update(
                {
                    "GG_RUNTIME_DATABASE_URL": (
                        "postgresql://gg_runtime:"
                        f"{quote(password, safe='')}@127.0.0.1:54322/"
                        "postgres?sslmode=disable"
                    ),
                    "GG_RUNTIME_TEST_SCHEMA": schema,
                    "PYTHONPATH": os.pathsep.join(
                        (
                            str(ROOT / "backend"),
                            str(ROOT / "packages/gg-sdk"),
                            str(ROOT),
                        )
                    ),
                    "PYTHONDONTWRITEBYTECODE": "1",
                }
            )
            return subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-p",
                    "no:cacheprovider",
                    *sys.argv[1:],
                ],
                cwd=ROOT,
                env=env,
                check=False,
            ).returncode
        finally:
            admin.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema))
            )
            if previous[0] is None:
                admin.execute("ALTER ROLE gg_runtime PASSWORD NULL")
            else:
                admin.execute(
                    sql.SQL("ALTER ROLE gg_runtime PASSWORD {}").format(
                        sql.Literal(previous[0])
                    )
                )


if __name__ == "__main__":
    raise SystemExit(main())
