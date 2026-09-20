from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path

import modal
import pytest

from gg.runtime import modal_image


def test_modal_sdk_and_runtime_versions_are_pinned() -> None:
    assert modal.__version__ == modal_image.MODAL_SDK_VERSION == "1.5.5"
    assert modal_image.version_evidence() == {
        "image": "gg-agent-server:2026-09-20-v1",
        "modal": "1.5.5",
        "python": "3.12.11",
        "uv": "0.11.2",
        "node": "22.23.1",
        "pi": "0.83.0",
        "git": "2.39.5",
        "gh": "2.100.0",
    }


def test_dockerfile_matches_standard_modal_image_evidence() -> None:
    source = (Path(__file__).resolve().parents[3] / "Dockerfile").read_text()

    assert "ARG PYTHON_VERSION=3.12.11" in source
    assert "ghcr.io/astral-sh/uv:0.11.2" in source
    assert "node:22.23.1-bookworm-slim" in source
    assert "@earendil-works/pi-coding-agent@0.83.0" in source
    assert "git=1:2.39.5-0+deb12u3" in source
    assert "gh_2.100.0_linux_${TARGETARCH}.tar.gz" in source


def test_standard_image_uses_no_nested_docker_or_vm_beta() -> None:
    source = (Path(__file__).resolve().parents[3] / "Dockerfile").read_text()
    image_source = Path(modal_image.__file__).read_text()

    assert "docker-in-docker" not in source.lower()
    assert "vm_sandbox" not in image_source.lower()
    assert "Image.from_dockerfile" in image_source


def _fake_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "packages" / "gg-server").mkdir(parents=True)
    (repo / "Dockerfile").write_text("FROM scratch\n")
    return repo


def test_repository_root_is_cwd_even_when_module_is_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _fake_repo(tmp_path)
    installed = (
        tmp_path
        / ".venv"
        / "lib"
        / "python3.12"
        / "site-packages"
        / "gg"
        / "runtime"
        / "modal_image.py"
    )
    installed.parent.mkdir(parents=True)
    installed.write_text("# installed copy\n")
    monkeypatch.chdir(repo / "packages")

    assert modal_image.find_repository_root() == repo.resolve()
    with pytest.raises(FileNotFoundError, match="repository root"):
        modal_image.find_repository_root(start=installed)


def test_build_and_publish_uses_repo_dockerfile_not_venv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _fake_repo(tmp_path)
    captured: dict[str, object] = {}

    class FakeImage:
        def build(self, app: object) -> FakeImage:
            del app
            return self

        def publish(self, image_name: str) -> None:
            captured["published"] = image_name

    monkeypatch.setattr(modal_image.modal, "enable_output", lambda: nullcontext())
    monkeypatch.setattr(
        modal_image.modal.App, "lookup", staticmethod(lambda *args, **kwargs: object())
    )
    monkeypatch.setattr(
        modal_image.modal.Image,
        "from_dockerfile",
        staticmethod(
            lambda path, **kwargs: (
                captured.update({"path": path, **kwargs}) or FakeImage()
            )
        ),
    )

    modal_image.build_and_publish(context_dir=repo)

    assert captured["path"] == repo / "Dockerfile"
    assert captured["context_dir"] == repo.resolve()
    assert captured["published"] == "gg-agent-server:2026-09-20-v1"


def test_repository_root_missing_dockerfile_is_explicit(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="repository root"):
        modal_image.find_repository_root(start=tmp_path)
