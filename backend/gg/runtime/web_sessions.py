"""Private profile and Auth session checks through the bounded runtime role."""

from uuid import UUID

from psycopg_pool import ConnectionPool


class PostgresWebSessions:
    def __init__(self, pool: ConnectionPool) -> None:
        self.pool = pool

    def active(self, user_id: str, session_id: str) -> bool:
        with self.pool.connection() as connection:
            row = connection.execute(
                "select app_private.web_session_active(%s, %s)",
                (UUID(user_id), UUID(session_id)),
            ).fetchone()
            return bool(row and row[0])

    def ensure_profile(self, user_id: str, session_id: str) -> bool:
        with self.pool.connection() as connection, connection.transaction():
            row = connection.execute(
                "select app_private.web_session_active(%s, %s)",
                (UUID(user_id), UUID(session_id)),
            ).fetchone()
            if not row or not row[0]:
                return False
            connection.execute("select set_config('app.user_id', %s, true)", (user_id,))
            connection.execute(
                "insert into app_private.profiles (id) values (%s) "
                "on conflict do nothing",
                (UUID(user_id),),
            )
            return True
