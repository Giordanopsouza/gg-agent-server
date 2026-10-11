"""Build React into the runtime image; Node is used only during image build."""

import hashlib

import modal

from gg.runtime.modal_image import find_repository_root


def runtime_version() -> str:
    root = find_repository_root()
    digest = hashlib.sha256()
    paths = sorted(
        path
        for directory in ("backend/gg", "packages/gg-sdk/gg", "frontend/src")
        for path in (root / directory).rglob("*")
        if path.is_file() and path.suffix in {".py", ".ts", ".tsx", ".css"}
    )
    paths += [
        root / "frontend" / name
        for name in (
            "package.json",
            "package-lock.json",
            "index.html",
            "vite.config.ts",
        )
    ]
    for path in paths:
        digest.update(str(path.relative_to(root)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def runtime_image() -> modal.Image:
    root = find_repository_root()
    return (
        modal.Image.debian_slim(python_version="3.12")
        .apt_install("curl", "xz-utils")
        .run_commands(
            "curl -fsSL https://nodejs.org/dist/v22.23.1/"
            "node-v22.23.1-linux-x64.tar.xz "
            "| tar -xJ -C /usr/local --strip-components=1"
        )
        .add_local_dir(
            root / "frontend",
            "/app/frontend",
            copy=True,
            ignore=["node_modules", "dist", "dist-server", ".env*"],
        )
        .run_commands(
            "cd /app/frontend && npm ci && npm run build",
            "rm -rf /app/frontend/node_modules /usr/local/bin/node "
            "/usr/local/bin/npm /usr/local/bin/npx",
        )
        .add_local_dir(
            root / "packages/gg-sdk",
            "/app/packages/gg-sdk",
            copy=True,
            ignore=["build", "*.egg-info", "__pycache__", "tests"],
        )
        .add_local_dir(
            root / "backend",
            "/app/backend",
            copy=True,
            ignore=["build", "*.egg-info", "__pycache__", "tests", ".*cache"],
        )
        .pip_install("/app/packages/gg-sdk", "/app/backend")
        .env(
            {
                "GG_WEB_DIST_PATH": "/app/frontend/dist",
                "GG_RUNTIME_VERSION": runtime_version(),
            }
        )
    )
