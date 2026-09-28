"""Read-only production login check; requires the server-only database URL."""

from urllib.parse import urlsplit

from gg.runtime.postgres import PRODUCTION_POOLER_HOST, RuntimePostgres


def main() -> None:
    config = RuntimePostgres.from_env()
    if urlsplit(config.url).hostname != PRODUCTION_POOLER_HOST:
        raise SystemExit("This check requires the production Session pooler URL")

    engine = config.engine()
    try:
        with engine.connect() as connection:
            role, timeout = connection.exec_driver_sql(
                "select current_user, current_setting('statement_timeout')"
            ).fetchone()
            if (role, timeout) != ("gg_runtime", "15s"):
                raise AssertionError("Unexpected runtime role or statement timeout")

            can_use_auth, can_create_schema, visible_profiles = (
                connection.exec_driver_sql(
                    """select
                        has_schema_privilege(current_user, 'auth', 'USAGE'),
                        has_schema_privilege(current_user, 'app_private', 'CREATE'),
                        (select count(*) from app_private.profiles)"""
                ).fetchone()
            )
            if can_use_auth or can_create_schema or visible_profiles:
                raise AssertionError(
                    "Production role or profile isolation is too broad"
                )
    finally:
        engine.dispose()

    print("Production Session pooler login, CA verification, role and RLS passed")


if __name__ == "__main__":
    main()
