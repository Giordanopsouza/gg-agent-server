from __future__ import annotations

import ast
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER_ROOT = REPO_ROOT / "packages" / "gg-server" / "gg" / "server"
# - # config.py is the single module allowed to read the environment.
ALLOWED_MODULE = "config.py"

_ENV_NAMES = {"environ", "getenv"}


def _iter_python_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if path.is_file())


def _relative_path(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def _env_violations(tree: ast.AST) -> list[str]:
    """Return human-readable descriptions of any os.environ/os.getenv usage."""
    offenders: list[str] = []

    for child in ast.walk(tree):
        # os.environ / os.getenv attribute access
        if isinstance(child, ast.Attribute) and child.attr in _ENV_NAMES:
            if isinstance(child.value, ast.Name) and child.value.id == "os":
                offenders.append(f"uses os.{child.attr}")
        # from os import environ, getenv
        if isinstance(child, ast.ImportFrom) and child.module == "os":
            for alias in child.names:
                if alias.name in _ENV_NAMES:
                    offenders.append(f"imports os.{alias.name}")
        # bare environ/getenv name usage (after `from os import ...`)
        if isinstance(child, ast.Name) and child.id in _ENV_NAMES:
            offenders.append(f"references {child.id}")

    return offenders


@pytest.mark.parametrize(
    "path",
    _iter_python_files(SERVER_ROOT),
    ids=_relative_path,
)
def test_no_env_access_outside_config(path: Path) -> None:
    # - # Every gg.server module except config.py must stay off os.environ/getenv.
    if path.name == ALLOWED_MODULE:
        return

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    offenders = _env_violations(tree)
    assert not offenders, (
        f"{path} reads env outside config.py: {offenders}. "
        "Use gg.server.get_settings() instead."
    )
