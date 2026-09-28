"""Exercise fresh creation, adoption, drift, and safe downgrade in local Postgres."""

from __future__ import annotations

import os
import secrets
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
from psycopg import sql


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ADMIN_URL = (
    "postgresql://postgres:postgres@127.0.0.1:54322/postgres?sslmode=disable"
)


def database_url(admin_url: str, database: str) -> str:
    parsed = urlsplit(admin_url)
    return urlunsplit(parsed._replace(path=f"/{database}"))


def alembic(
    url: str, *args: str, expected: int = 0
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "GG_MIGRATION_DATABASE_URL": url,
            "PYTHONPATH": str(ROOT / "backend"),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(ROOT / "backend/alembic.ini"),
            *args,
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != expected:
        raise AssertionError(
            f"Alembic {' '.join(args)} returned {result.returncode}:\n"
            f"{result.stdout}\n{result.stderr}"
        )
    return result


def github_store_contract(test_url: str) -> None:
    """Use the bounded runtime role against a real fresh Postgres schema."""
    from uuid import uuid4

    from cryptography.fernet import Fernet
    from sqlalchemy import create_engine
    from sqlalchemy.exc import IntegrityError

    from gg.runtime.github_connection import PostgresGitHubConnections

    first, second = str(uuid4()), str(uuid4())
    session = str(uuid4())
    with psycopg.connect(test_url) as admin:
        for owner in (first, second):
            admin.execute("insert into auth.users(id) values (%s)", (owner,))
            admin.execute("insert into app_private.profiles(id) values (%s)", (owner,))
        assert not admin.execute(
            "select has_table_privilege('authenticated', "
            "'vault_private.github_connections', 'select')"
        ).fetchone()[0]
        assert not admin.execute(
            "select has_table_privilege('anon', "
            "'app_private.github_installations', 'select')"
        ).fetchone()[0]
    runtime_url = os.getenv("GG_RUNTIME_DATABASE_URL")
    if not runtime_url:
        print("GitHub store role contract skipped: no local gg_runtime URL")
        return
    if urlsplit(runtime_url).hostname not in {"localhost", "127.0.0.1"}:
        raise RuntimeError("GitHub store contract requires a local gg_runtime URL")
    runtime_test_url = database_url(runtime_url, urlsplit(test_url).path.lstrip("/"))
    engine = create_engine(
        runtime_test_url.replace("postgresql://", "postgresql+psycopg://")
    )

    store = PostgresGitHubConnections(engine, Fernet.generate_key().decode())
    state = secrets.token_urlsafe(32)
    store.begin(first, session, state)
    assert not store.consume(second, session, state)
    assert store.consume(first, session, state)
    assert not store.consume(first, session, state)
    installations = [
        {"id": 123, "account_login": "example", "account_type": "Organization"}
    ]
    store.connect(first, 42, "alice", "user-access-secret", installations)
    assert store.current(first) == (42, "alice", "user-access-secret", "connected")
    assert store.current(second) is None
    try:
        store.connect(second, 42, "alice", "other-secret", installations)
        raise AssertionError("a GitHub user was linked to two owners")
    except IntegrityError:
        pass
    with psycopg.connect(test_url) as admin:
        ciphertext = admin.execute(
            "select token_ciphertext from vault_private.github_connections "
            "where owner_id=%s",
            (first,),
        ).fetchone()[0]
        assert b"user-access-secret" not in ciphertext
    delivery = uuid4()
    assert store.webhook(delivery, "installation", "deleted", 123, None)
    assert not store.webhook(delivery, "installation", "deleted", 123, None)
    with psycopg.connect(test_url) as admin:
        status = admin.execute(
            "select status from app_private.github_installations "
            "where owner_id=%s and installation_id=123",
            (first,),
        ).fetchone()[0]
        assert status == "removed"
    assert store.refresh(first, 42, installations)["status"] == "connected"
    assert store.webhook(uuid4(), "github_app_authorization", "revoked", None, 42)
    assert store.current(first)[3] == "revoked"
    assert store.current(first)[2] is None
    store.disconnect(first)
    assert store.current(first) is None
    engine.dispose()


def main() -> None:
    admin_url = os.getenv("GG_LOCAL_ADMIN_DATABASE_URL", DEFAULT_ADMIN_URL)
    if urlsplit(admin_url).hostname not in {"127.0.0.1", "localhost"}:
        raise SystemExit("Alembic tests require a local Postgres admin URL")

    name = f"alembic_test_{secrets.token_hex(6)}"
    test_url = database_url(admin_url, name)
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute(sql.SQL("create database {}").format(sql.Identifier(name)))
        try:
            with psycopg.connect(test_url) as connection:
                connection.execute("create schema auth")
                connection.execute(
                    "create table auth.users ("
                    "id uuid primary key, deleted_at timestamptz, "
                    "banned_until timestamptz)"
                )
                connection.execute(
                    "create table auth.sessions ("
                    "id uuid primary key, user_id uuid not null, "
                    "not_after timestamptz)"
                )

            alembic(test_url, "upgrade", "head")
            alembic(test_url, "check")
            github_store_contract(test_url)
            with psycopg.connect(test_url) as connection:
                assert connection.execute(
                    "select version_num from runtime_private.alembic_version"
                ).fetchone() == ("0003_github_connection",)
                assert connection.execute(
                    "select value from runtime_private.schema_meta "
                    "where key = 'schema_version'"
                ).fetchone() == ("8",)
            alembic(test_url, "downgrade", "0001_application_baseline")
            with psycopg.connect(test_url) as connection:
                connection.execute(
                    "insert into runtime_private.tasks ("
                    "id, seq, state, idempotency_key, repository, prompt, "
                    "created_at, updated_at) values ("
                    "'adoption-proof', 1, 'completed', 'adoption-proof', '', '', "
                    "'2026-09-28T00:00:00+00:00', "
                    "'2026-09-28T00:00:00+00:00')"
                )
                connection.execute("delete from runtime_private.alembic_version")

            alembic(test_url, "upgrade", "head")
            with psycopg.connect(test_url) as connection:
                assert connection.execute(
                    "select count(*) from runtime_private.tasks "
                    "where id = 'adoption-proof'"
                ).fetchone() == (1,)

            downgrade = alembic(test_url, "downgrade", "base", expected=1)
            if "cannot be downgraded safely" not in downgrade.stderr:
                raise AssertionError(downgrade.stderr)
            with psycopg.connect(test_url) as connection:
                assert connection.execute(
                    "select version_num from runtime_private.alembic_version"
                ).fetchone() == ("0003_github_connection",)
        finally:
            admin.execute(
                sql.SQL("drop database {} with (force)").format(sql.Identifier(name))
            )

    print("Alembic fresh creation, adoption, drift and safe downgrade passed")


if __name__ == "__main__":
    main()
