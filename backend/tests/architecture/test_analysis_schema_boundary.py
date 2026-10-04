"""Analysis DTOs must remain pure through every project-local import hop."""

from __future__ import annotations

import ast
import subprocess
import sys
from collections import deque
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2] / "app"
FORBIDDEN_ROOTS = {"db", "fastapi", "sqlalchemy", "starlette"}


def _local_source(root: Path, module: str) -> Path | None:
    path = root.joinpath(*module.split("."))
    for source in (path.with_suffix(".py"), path / "__init__.py"):
        if source.is_file():
            return source
    return None


def _dependencies(root: Path, module: str, source: Path) -> set[str]:
    package = module if source.name == "__init__.py" else module.rpartition(".")[0]
    imports: set[str] = set()
    for node in ast.walk(ast.parse(source.read_text())):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                parts = package.split(".")
                parent = ".".join(parts[: len(parts) - node.level + 1])
                base = ".".join(part for part in (parent, node.module) if part)
            else:
                base = node.module or ""
            if base:
                imports.add(base)
                imports.update(
                    f"{base}.{alias.name}"
                    for alias in node.names
                    if _local_source(root, f"{base}.{alias.name}") is not None
                )
    # Python executes package initializers before their imported children.
    for dependency in tuple(imports):
        parts = dependency.split(".")
        imports.update(
            ".".join(parts[:index])
            for index in range(1, len(parts))
            if root.joinpath(*parts[:index], "__init__.py").is_file()
        )
    return imports


def _impure_dependency_paths(root: Path, entry: str) -> tuple[tuple[str, ...], ...]:
    pending = deque([(entry,)])
    parts = entry.split(".")
    pending.extend(
        (entry, ".".join(parts[:index]))
        for index in range(1, len(parts))
        if root.joinpath(*parts[:index], "__init__.py").is_file()
    )
    visited: set[str] = set()
    violations: list[tuple[str, ...]] = []
    while pending:
        chain = pending.popleft()
        module = chain[-1]
        if module in visited:
            continue
        visited.add(module)
        if module.split(".")[0] in FORBIDDEN_ROOTS or module.endswith((".models", "_models")):
            violations.append(chain)
            continue
        source = _local_source(root, module)
        if source is not None:
            pending.extend(
                (*chain, dependency) for dependency in sorted(_dependencies(root, module, source))
            )
    return tuple(violations)


def test_analysis_schema_recursive_dependencies_are_pure() -> None:
    violations = _impure_dependency_paths(APP, "analysis.schemas")
    assert not violations, "\n".join(" -> ".join(chain) for chain in violations)


@pytest.mark.parametrize(
    "indirect_import",
    [
        "from sqlalchemy.orm import Session",
        "from db.session import create_session_factory",
        "from content.models import ContentObservation",
        "from fastapi import FastAPI",
        "from starlette.requests import Request",
    ],
)
def test_recursive_schema_guard_rejects_impure_indirect_dependencies(
    tmp_path: Path, indirect_import: str
) -> None:
    package = tmp_path / "sample"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "schemas.py").write_text("from . import contracts as contracts\n")
    (package / "contracts.py").write_text(f"{indirect_import}\nfrom .schemas import Manifest\n")
    assert _impure_dependency_paths(tmp_path, "sample.schemas")


def test_recursive_schema_guard_checks_parent_package_initializers(tmp_path: Path) -> None:
    package = tmp_path / "sample"
    package.mkdir()
    (package / "__init__.py").write_text("from sqlalchemy.orm import Session\n")
    (package / "schemas.py").write_text("class Manifest: pass\n")
    assert _impure_dependency_paths(tmp_path, "sample.schemas")


def test_analysis_schema_import_does_not_load_persistence_or_http() -> None:
    code = (
        "import importlib, sys; "
        f"sys.path.insert(0, {str(APP)!r}); "
        "importlib.import_module('analysis.schemas'); "
        "forbidden = [name for name in sys.modules "
        "if name.split('.')[0] in {'db', 'fastapi', 'sqlalchemy', 'starlette'} "
        "or name.endswith(('.models', '_models'))]; "
        "assert not forbidden, forbidden"
    )
    subprocess.run([sys.executable, "-c", code], check=True, timeout=10, capture_output=True)
