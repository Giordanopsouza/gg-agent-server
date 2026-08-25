from __future__ import annotations

import ast
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOT = REPO_ROOT / "packages" / "gg-server" / "gg" / "runtime"


def _iter_python_files() -> list[Path]:
    return sorted(path for path in RUNTIME_ROOT.rglob("*.py") if path.is_file())


def _imports_server(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            offenders.extend(
                alias.name
                for alias in node.names
                if alias.name == "gg.server" or alias.name.startswith("gg.server.")
            )
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            if node.module == "gg.server" or node.module.startswith("gg.server."):
                offenders.append(node.module)
    return sorted(offenders)


@pytest.mark.parametrize("path", _iter_python_files(), ids=lambda path: path.name)
def test_runtime_process_does_not_import_sandbox_server(path: Path) -> None:
    assert not _imports_server(path)
