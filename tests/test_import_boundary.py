from __future__ import annotations

import ast
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SDK_ROOT = REPO_ROOT / "packages" / "gg-sdk" / "gg" / "sdk"


def _iter_python_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if path.is_file())


def _imported_modules(node: ast.AST) -> set[str]:
    modules: set[str] = set()

    for child in ast.walk(node):
        if isinstance(child, ast.Import):
            for alias in child.names:
                modules.add(alias.name)
        elif isinstance(child, ast.ImportFrom) and child.module is not None:
            modules.add(child.module)
            modules.update(f"{child.module}.{alias.name}" for alias in child.names)

    return modules


def _violates_boundary(module_name: str) -> bool:
    return module_name == "gg.server" or module_name.startswith("gg.server.")


def _relative_path(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


@pytest.mark.parametrize(
    "path",
    _iter_python_files(SDK_ROOT),
    ids=_relative_path,
)
def test_sdk_does_not_import_server(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    offenders = sorted(
        module_name
        for module_name in _imported_modules(tree)
        if _violates_boundary(module_name)
    )
    assert not offenders, f"{path} imports forbidden server modules: {offenders}"


def test_boundary_detector_rejects_from_gg_import_server() -> None:
    tree = ast.parse("from gg import server")

    assert any(_violates_boundary(module) for module in _imported_modules(tree))
