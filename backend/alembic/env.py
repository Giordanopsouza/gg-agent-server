"""Alembic environment for application-owned Supabase schemas."""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text
from sqlalchemy.engine import make_url

from gg.runtime.db_models import APPLICATION_SCHEMAS, Base, include_in_migrations


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _migration_url() -> str:
    raw = os.environ.get("GG_MIGRATION_DATABASE_URL")
    if not raw:
        raise RuntimeError("GG_MIGRATION_DATABASE_URL is required by Alembic")
    url = make_url(raw)
    if url.get_backend_name() != "postgresql":
        raise RuntimeError("Alembic requires a Postgres migration URL")
    if (url.username or "").startswith("gg_runtime"):
        raise RuntimeError("Alembic refuses the least-privilege runtime role")
    return url.set(drivername="postgresql+psycopg").render_as_string(
        hide_password=False
    )


def _include_name(
    name: str | None, type_: str, parent_names: dict[str, str | None]
) -> bool:
    if type_ == "schema":
        return name in APPLICATION_SCHEMAS
    if type_ == "table":
        return parent_names.get("schema_name") in APPLICATION_SCHEMAS
    return True


def _configure(connection: object | None = None) -> None:
    context.configure(
        connection=connection,
        url=None if connection is not None else _migration_url(),
        target_metadata=target_metadata,
        include_schemas=True,
        include_name=_include_name,
        include_object=include_in_migrations,
        compare_type=True,
        compare_server_default=True,
        version_table_schema="runtime_private",
        literal_binds=connection is None,
        dialect_opts={"paramstyle": "named"} if connection is None else None,
    )


def run_migrations_offline() -> None:
    _configure()
    with context.begin_transaction():
        context.execute("CREATE SCHEMA IF NOT EXISTS runtime_private")
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = _migration_url()
    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args={"prepare_threshold": None},
    )
    with connectable.connect() as connection:
        connection.execute(text("CREATE SCHEMA IF NOT EXISTS runtime_private"))
        connection.commit()
        _configure(connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
