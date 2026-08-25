from __future__ import annotations

from typing import Any

import pytest

from gg.runtime import app as runtime_app
from gg.runtime.app import DockerSandboxLauncher


class FakeDockerWorkspace:
    instances: list[FakeDockerWorkspace] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.host = "http://127.0.0.1:49152"
        self.entered = False
        self.stopped = False
        self.__class__.instances.append(self)

    def __enter__(self) -> FakeDockerWorkspace:
        self.entered = True
        return self

    def stop(self) -> None:
        self.stopped = True


def test_launcher_uses_image_and_session_key_then_owns_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeDockerWorkspace.instances.clear()
    monkeypatch.setattr(runtime_app, "DockerWorkspace", FakeDockerWorkspace)

    sandbox = DockerSandboxLauncher(image="gg-agent-server:dev").start(
        "sandbox-secret"
    )
    workspace = FakeDockerWorkspace.instances[0]

    assert workspace.kwargs == {
        "image": "gg-agent-server:dev",
        "api_key": "sandbox-secret",
    }
    assert workspace.entered
    assert sandbox.url == "http://127.0.0.1:49152"

    sandbox.stop()
    assert workspace.stopped
