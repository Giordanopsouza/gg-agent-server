"""Build and publish the versioned standard Modal sandbox image."""

from __future__ import annotations

import argparse
from pathlib import Path

import modal

from gg.runtime.config import DEFAULT_MODAL_APP_NAME, DEFAULT_MODAL_IMAGE_NAME


MODAL_SDK_VERSION = "1.5.5"
PYTHON_VERSION = "3.12.11"
UV_VERSION = "0.11.2"
NODE_VERSION = "22.23.1"
PI_VERSION = "0.83.0"
GIT_VERSION = "2.39.5"
GH_VERSION = "2.100.0"


def version_evidence() -> dict[str, str]:
    return {
        "image": DEFAULT_MODAL_IMAGE_NAME,
        "modal": MODAL_SDK_VERSION,
        "python": PYTHON_VERSION,
        "uv": UV_VERSION,
        "node": NODE_VERSION,
        "pi": PI_VERSION,
        "git": GIT_VERSION,
        "gh": GH_VERSION,
    }


def build_and_publish(
    *,
    app_name: str = DEFAULT_MODAL_APP_NAME,
    image_name: str = DEFAULT_MODAL_IMAGE_NAME,
) -> None:
    """Build the repository Dockerfile on Modal and publish its named image."""

    repository_root = Path(__file__).resolve().parents[4]
    with modal.enable_output():
        app = modal.App.lookup(app_name, create_if_missing=True)
        image = modal.Image.from_dockerfile(
            repository_root / "Dockerfile",
            context_dir=repository_root,
            build_args={
                "PYTHON_VERSION": PYTHON_VERSION,
                # Dockerfile's pinned gh checksums are architecture-specific.
                "TARGETARCH": "amd64",
            },
        )
        image.build(app=app).publish(image_name)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", default=DEFAULT_MODAL_APP_NAME)
    parser.add_argument("--image", default=DEFAULT_MODAL_IMAGE_NAME)
    parser.add_argument("--print-versions", action="store_true")
    args = parser.parse_args()
    if args.print_versions:
        for name, version in version_evidence().items():
            print(f"{name}={version}")
        return
    build_and_publish(app_name=args.app, image_name=args.image)


if __name__ == "__main__":
    main()
