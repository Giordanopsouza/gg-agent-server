"""Fixed WPP credentials use the same ownership boundary as browser sessions."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from gg.runtime.app import create_app
from gg.runtime.config import RuntimeSettings, load_settings
from test_support.sqlite_ledger import new_ledger


@pytest.fixture
def wpp_app(tmp_path):
    ledger = new_ledger()
    owner = uuid4()
    with ledger.db.write() as tx:
        tx.connection.execute(
            "INSERT INTO local_users VALUES (?, ?, ?)",
            (str(owner), "google-sub", "owner@example.test"),
        )
    settings = RuntimeSettings(
        api_key="operator",
        wpp_api_token="wpp-secret",
        wpp_owner_id=owner,
        dispatch_lock_path=str(tmp_path / "lock"),
    )
    with TestClient(create_app(settings, task_ledger=ledger)) as client:
        yield client, owner, ledger


def test_wpp_owned_submission_isolation_and_socket(wpp_app):
    client, owner, ledger = wpp_app
    headers = {"Authorization": "Bearer wpp-secret"}
    body = {"prompt": "hello", "idempotency_key": "same-key"}
    first = client.post("/tasks", headers=headers, json=body)
    assert first.status_code == 201
    assert first.json()["owner_id"] == str(owner)
    assert client.post("/tasks", headers=headers, json=body).status_code == 200
    other = client.post("/tasks", headers={"X-API-Key": "operator"}, json=body)
    assert other.status_code == 201
    assert other.json()["owner_id"] is None
    assert [t["id"] for t in client.get("/tasks", headers=headers).json()] == [
        first.json()["id"]
    ]
    assert (
        client.get(f"/tasks/{other.json()['id']}", headers=headers).status_code == 404
    )
    assert client.get("/tasks/dispatch/status", headers=headers).status_code == 403
    assert client.get("/ready", headers=headers).status_code == 401
    assert (
        client.post(
            "/tasks", headers=headers, json={**body, "owner_id": str(uuid4())}
        ).status_code
        == 422
    )
    with client.websocket_connect(
        f"/tasks/sockets/events/{first.json()['id']}", headers=headers
    ):
        pass
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            f"/tasks/sockets/events/{other.json()['id']}", headers=headers
        ):
            pass
    assert ledger.get(first.json()["id"]).owner_id == owner


@pytest.mark.parametrize(
    "authorization",
    ["Bearer wrong", "Basic wpp-secret", "Bearer", "Bearer wpp-secret "],
)
def test_invalid_bearer_never_falls_back_to_operator_or_cookie(wpp_app, authorization):
    client, _, _ = wpp_app
    assert (
        client.get("/tasks", headers={"Authorization": authorization}).status_code
        == 401
    )
    assert (
        client.get(
            "/tasks", headers={"Authorization": authorization, "X-API-Key": "operator"}
        ).status_code
        == 401
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"wpp_api_token": "secret"},
        {"wpp_owner_id": str(uuid4())},
        {"wpp_api_token": "operator", "wpp_owner_id": str(uuid4())},
        {"wpp_api_token": "bad token", "wpp_owner_id": str(uuid4())},
        {"wpp_api_token": "secret", "wpp_owner_id": "not-a-uuid"},
    ],
)
def test_invalid_configuration(overrides):
    with pytest.raises(ValueError):
        RuntimeSettings(api_key="operator", **overrides)


def test_nonexistent_owner_fails_startup(tmp_path):
    settings = RuntimeSettings(
        api_key="operator",
        wpp_api_token="secret",
        wpp_owner_id=uuid4(),
        dispatch_lock_path=str(tmp_path / "lock"),
    )
    with pytest.raises(ValueError, match="existing account"):
        with TestClient(create_app(settings, task_ledger=new_ledger())):
            pass


def test_environment_binding(monkeypatch):
    owner = uuid4()
    monkeypatch.setenv("GG_RUNTIME_API_KEY", "operator")
    monkeypatch.setenv("GG_WPP_API_TOKEN", "secret")
    monkeypatch.setenv("GG_WPP_OWNER_ID", str(owner))
    settings = load_settings()
    assert settings.wpp_owner_id == owner
    assert settings.wpp_api_token == "secret"
    assert "wpp_api_token=" not in repr(settings)


def test_gg_submit_cli_creates_an_owned_task(wpp_app, monkeypatch):
    import json

    from click.testing import CliRunner

    from gg.sdk.cli import main as cli_module
    from gg.sdk.task_client import TaskClient
    from gg.sdk.task_settings import load_task_client_settings

    client, owner, _ = wpp_app
    monkeypatch.setenv("GG_TASK_API_TOKEN", "wpp-secret")
    monkeypatch.setenv("GG_RUNTIME_API_KEY", "stale-key")
    monkeypatch.setattr(
        cli_module,
        "_open_client",
        lambda: TaskClient(load_task_client_settings(), client=client),
    )
    result = CliRunner().invoke(
        cli_module.main,
        ["--json", "submit", "--prompt", "CLI proof", "--idempotency-key", "cli-proof"],
    )
    assert result.exit_code == 0, result.output
    body = json.loads(result.output)
    assert body["task"]["owner_id"] == str(owner)
