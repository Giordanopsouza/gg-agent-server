"""Run runtime tests in a disposable schema on local Supabase Postgres."""

from __future__ import annotations

import os
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote, urlsplit

import psycopg
from psycopg import sql
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from gg.runtime.db_models import Base
from gg.runtime.ledger import SUPPORTED_SCHEMA_VERSION


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ADMIN_URL = (
    "postgresql://postgres:postgres@127.0.0.1:54322/postgres?sslmode=disable"
)


def create_runtime_schema(admin_url: str, schema: str) -> None:
    """Build an isolated ledger from the same metadata Alembic compares."""
    url = make_url(admin_url).set(drivername="postgresql+psycopg")
    engine = create_engine(url, connect_args={"prepare_threshold": None})
    runtime_tables = [
        table
        for table in Base.metadata.sorted_tables
        if table.schema == "runtime_private"
    ]
    try:
        with engine.begin() as connection:
            translated = connection.execution_options(
                schema_translate_map={"runtime_private": schema}
            )
            Base.metadata.create_all(translated, tables=runtime_tables)
            translated.execute(
                Base.metadata.tables["runtime_private.schema_meta"]
                .insert()
                .values(key="schema_version", value=str(SUPPORTED_SCHEMA_VERSION))
            )
            quoted_schema = connection.dialect.identifier_preparer.quote(schema)
            connection.execute(
                text(f"grant usage on schema {quoted_schema} to gg_runtime")
            )
            connection.execute(
                text(f"grant select on {quoted_schema}.schema_meta to gg_runtime")
            )
            data_tables = ", ".join(
                f"{quoted_schema}."
                + connection.dialect.identifier_preparer.quote(table.name)
                for table in runtime_tables
                if table.name != "schema_meta"
            )
            connection.execute(
                text(
                    "grant select, insert, update, delete on "
                    f"{data_tables} to gg_runtime"
                )
            )
    finally:
        engine.dispose()


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
            create_runtime_schema(admin_url, schema)
            admin.execute(
                sql.SQL("ALTER ROLE gg_runtime PASSWORD {}").format(
                    sql.Literal(password)
                )
            )
            with tempfile.TemporaryDirectory(prefix="gg-postgres-tests-") as temp_dir:
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
                                str(ROOT / "sandboxes"),
                                str(ROOT),
                            )
                        ),
                        "PYTHONDONTWRITEBYTECODE": "1",
                        "TMPDIR": temp_dir,
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
