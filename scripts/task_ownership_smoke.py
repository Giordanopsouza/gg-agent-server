"""Exercise task ownership with two real local Supabase Auth sessions.

Run with GG_RUNTIME_DATABASE_URL pointed at local Supabase Postgres. The smoke
creates two temporary Auth users and tasks, then removes exactly those rows.
"""

from __future__ import annotations

import json
import secrets
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
import psycopg
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from gg.runtime.app import create_app
from gg.runtime.config import RuntimeSettings
from gg.runtime.ledger import TaskLedger
from gg.runtime.postgres import RuntimePostgres
from gg.runtime.web_auth import SESSION_COOKIE, SupabaseAuth
from gg.runtime.web_sessions import PostgresWebSessions


def local_status() -> dict[str, str]:
    result = subprocess.run(
        ["supabase", "status", "-o", "json"],
        check=True,
        capture_output=True,
        text=True,
    )
    output = result.stdout
    return json.loads(output[output.index("{") :])


def main() -> None:
    status = local_status()
    api_url = status["API_URL"]
    database = RuntimePostgres.from_env()
    if urlsplit(api_url).hostname not in {"localhost", "127.0.0.1"} or urlsplit(
        database.url
    ).hostname not in {"localhost", "127.0.0.1"}:
        raise RuntimeError("ownership smoke requires local Supabase")
    publishable = status["PUBLISHABLE_KEY"]
    users: list[str] = []
    tasks: list[str] = []
    direct_statuses: list[int] = []
    ledger = TaskLedger(database)
    try:
        tokens = []
        with httpx.Client(base_url=api_url, timeout=10) as auth_client:
            for _ in range(2):
                signup = auth_client.post(
                    "/auth/v1/signup",
                    headers={"apikey": publishable},
                    json={
                        "email": f"task-ownership-{uuid4().hex}@example.test",
                        "password": secrets.token_urlsafe(24),
                    },
                )
                signup.raise_for_status()
                data = signup.json()
                users.append(data["user"]["id"])
                tokens.append(data)
            for bearer in (None, tokens[0]["access_token"]):
                headers = {
                    "apikey": publishable,
                    "Accept-Profile": "runtime_private",
                }
                if bearer:
                    headers["Authorization"] = f"Bearer {bearer}"
                direct = auth_client.get("/rest/v1/tasks?select=id", headers=headers)
                assert direct.status_code == 406, direct.status_code
                direct_statuses.append(direct.status_code)

        settings = RuntimeSettings(
            api_key=secrets.token_urlsafe(24),
            supabase_url=api_url,
            supabase_publishable_key=publishable,
            web_cookie_key=Fernet.generate_key().decode(),
            web_origin="https://app.example",
            task_dispatch_enabled=False,
            dispatch_lock_path=str(
                Path(tempfile.gettempdir()) / f"task062-{uuid4()}.lock"
            ),
        )
        provider = SupabaseAuth(settings)
        app = create_app(
            settings,
            task_ledger=ledger,
            web_auth=provider,
            web_sessions=PostgresWebSessions(ledger.engine),
        )
        key = f"task062-{uuid4()}"
        with TestClient(app, base_url="https://app.example") as client:
            for i, token in enumerate(tokens):
                client.cookies.set(
                    SESSION_COOKIE,
                    provider.seal(
                        {
                            "access": token["access_token"],
                            "refresh": token["refresh_token"],
                        }
                    ),
                )
                response = client.post(
                    "/tasks",
                    headers={"Origin": "https://app.example"},
                    json={"idempotency_key": key, "prompt": f"owner {i}"},
                )
                assert response.status_code == 201, response.text
                task_id = response.json()["id"]
                tasks.append(task_id)
                assert response.json()["owner_id"] == users[i]
                assert [task["id"] for task in client.get("/tasks").json()] == [task_id]
                if i:
                    assert client.get(f"/tasks/{tasks[0]}").status_code == 404
                    assert client.get(f"/tasks/{tasks[0]}/events").status_code == 404
                    assert client.get(f"/tasks/{tasks[0]}/result").status_code == 404
                    assert (
                        client.get(f"/tasks/{tasks[0]}/messages/foreign").status_code
                        == 404
                    )
                    assert (
                        client.post(
                            f"/tasks/{tasks[0]}/messages",
                            headers={"Origin": "https://app.example"},
                            json={"id": "foreign", "content": "cross-owner"},
                        ).status_code
                        == 404
                    )
                    assert (
                        client.post(
                            f"/tasks/{tasks[0]}/cancel",
                            headers={"Origin": "https://app.example"},
                        ).status_code
                        == 409
                    )
                    assert (
                        client.post(
                            f"/tasks/{tasks[0]}/retry",
                            headers={"Origin": "https://app.example"},
                            json={"idempotency_key": f"foreign-{uuid4()}"},
                        ).status_code
                        == 409
                    )
                    try:
                        with client.websocket_connect(
                            f"/tasks/sockets/events/{tasks[0]}",
                            headers={"Origin": "https://app.example"},
                        ):
                            raise AssertionError("cross-owner socket opened")
                    except WebSocketDisconnect as exc:
                        assert exc.code == 1008
            assert len(set(tasks)) == 2
        print(
            "Two real Auth sessions, owner isolation, and Data API denial passed "
            f"(anon/user HTTP {direct_statuses})"
        )
    finally:
        ledger.close()
        with psycopg.connect(status["DB_URL"]) as connection:
            for table in (
                "sandbox_creations",
                "task_reservations",
                "publication_intents",
                "task_supervisions",
                "task_event_copies",
                "task_message_receipts",
                "task_results",
                "retention_tombstones",
            ):
                connection.execute(
                    f"delete from runtime_private.{table} where task_id = any(%s)",
                    (tasks,),
                )
            connection.execute(
                "delete from runtime_private.tasks where id = any(%s)", (tasks,)
            )
            connection.execute("delete from auth.users where id = any(%s)", (users,))


if __name__ == "__main__":
    main()
