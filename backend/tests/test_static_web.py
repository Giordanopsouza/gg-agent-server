"""Real runtime routing with a small React build and SQLite state."""

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from gg.runtime.app import create_app
from gg.runtime.config import RuntimeSettings
from gg.runtime.db_cli import main


@pytest.fixture
def client(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>REACT</html>")
    (dist / "assets/app.js").write_text("console.log('react')")
    outside = tmp_path / "secret"
    outside.write_text("secret")
    (dist / "escape").symlink_to(outside)
    db, snapshot = tmp_path / "runtime.db", tmp_path / "snapshot.db"
    main(["init", "--db", str(db), "--snapshot", str(snapshot)])
    monkeypatch.setenv("GG_RUNTIME_DB_PATH", str(db))
    monkeypatch.setenv("GG_RUNTIME_SNAPSHOT_PATH", str(snapshot))
    settings = RuntimeSettings(
        api_key="operator",
        google_client_id="test",
        google_client_secret="test",
        web_origin="https://app.example",
        web_dist_path=str(dist),
        dispatch_lock_path=str(tmp_path / "dispatch.lock"),
    )
    with TestClient(create_app(settings), base_url=settings.web_origin) as test:
        yield test


def test_assets_navigation_and_api_precedence(client):
    for path in ("/", "/workspace/123", "/index.html"):
        response = client.get(path)
        assert response.status_code == 200 and "REACT" in response.text
        assert response.headers["cache-control"] == "no-store"
    assert client.get("/assets/app.js").headers["cache-control"] == "no-cache"
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/auth/session").status_code == 401
    for path in (
        "/auth/missing",
        "/tasks/missing/path",
        "/api/missing",
        "/webhooks/missing",
        "/assets/missing.js",
        "/missing.css",
        "/escape",
        "/%252e%252e/secret",
        "/.env",
    ):
        response = client.get(path)
        assert response.status_code >= 400 and "REACT" not in response.text
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/workspace/123"):
            pass
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/tasks/sockets/events/missing"):
            pass


@pytest.mark.parametrize(
    "headers",
    [
        {"Host": "evil.example"},
        {"X-Forwarded-Host": "evil.example"},
        {"X-Forwarded-Host": "app.example,evil.example"},
        {"Forwarded": "host=evil.example;proto=https"},
        {"X-Forwarded-Proto": "http"},
    ],
)
def test_forged_origin_rejected(client, headers):
    assert client.get("/", headers=headers).status_code == 400
    assert client.get("/auth/session", headers=headers).status_code == 400


def test_configured_forwarded_host_accepted(client):
    assert (
        client.get(
            "/",
            headers={
                "Host": "internal",
                "X-Forwarded-Host": "app.example",
                "X-Forwarded-Proto": "https",
            },
        ).status_code
        == 200
    )


def test_modal_internal_transport_is_explicit_and_redirects_are_public():
    from fastapi import FastAPI

    from gg.runtime.static_web import OriginGuard

    app = FastAPI()
    app.add_middleware(OriginGuard, origin="https://app.example", internal_proxy=True)

    @app.get("/route/")
    def route():
        return {"ok": True}

    with TestClient(
        app, base_url="http://172.20.2.140:8000", client=("172.20.0.1", 1234)
    ) as client:
        response = client.get("/route", follow_redirects=False)
        assert response.headers["location"] == "https://app.example/route/"
        assert (
            client.get(
                "/route/", headers={"X-Forwarded-Host": "evil.example"}
            ).status_code
            == 400
        )
        assert (
            client.get("/route/", headers={"Host": "evil.example"}).status_code == 400
        )
    with TestClient(
        app, base_url="http://172.20.2.140:8000", client=("8.8.8.8", 1234)
    ) as client:
        assert client.get("/route/").status_code == 400
