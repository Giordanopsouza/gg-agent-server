"""Private profile and Auth session checks through the bounded runtime role."""

from uuid import UUID

from sqlalchemy import Engine


class PostgresWebSessions:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def active(self, user_id: str, session_id: str) -> bool:
        with self.engine.connect() as connection:
            row = connection.exec_driver_sql(
                "select app_private.web_session_active(%s, %s)",
                (UUID(user_id), UUID(session_id)),
            ).fetchone()
            return bool(row and row[0])

    def ensure_profile(self, user_id: str, session_id: str) -> bool:
        with self.engine.begin() as connection:
            row = connection.exec_driver_sql(
                "select app_private.web_session_active(%s, %s)",
                (UUID(user_id), UUID(session_id)),
            ).fetchone()
            if not row or not row[0]:
                return False
            connection.exec_driver_sql(
                "select set_config('app.user_id', %s, true)", (user_id,)
            )
            connection.exec_driver_sql(
                "insert into app_private.profiles (id) values (%s) "
                "on conflict do nothing",
                (UUID(user_id),),
            )
            return True
