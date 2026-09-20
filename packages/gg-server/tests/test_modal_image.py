from __future__ import annotations

from pathlib import Path

import modal

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
