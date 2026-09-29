"""The production runtime serves the browser UI on the Auth origin."""

from unittest.mock import MagicMock

from starlette.testclient import TestClient

from gg.runtime import RuntimeSettings, create_app


def test_runtime_serves_bundled_frontend_and_api() -> None:
    app = create_app(RuntimeSettings(api_key="control-secret"), task_ledger=MagicMock())
    client = TestClient(app)

    index = client.get("/")
    assert index.status_code == 200
    assert index.headers["cache-control"] == "no-cache"
    assert "gg · Tasks" in index.text

    asset = index.text.split("/assets/", 1)[1].split('"', 1)[0]
    assert client.get(f"/assets/{asset}").status_code == 200
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/auth/session").status_code == 503
