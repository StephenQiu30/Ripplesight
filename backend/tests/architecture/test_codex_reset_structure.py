import ast
from pathlib import Path

from sqlalchemy import DateTime

from db.metadata import metadata
from monitors.codex_models import (
    CodexResetEvent,
    CodexResetEventPost,
    CodexResetMonitor,
    CodexResetMonitorVersion,
    CodexResetPost,
    CodexResetRecognition,
    CodexResetReview,
    CodexResetScanGap,
)

MODELS = (
    CodexResetMonitor,
    CodexResetMonitorVersion,
    CodexResetScanGap,
    CodexResetPost,
    CodexResetRecognition,
    CodexResetEvent,
    CodexResetEventPost,
    CodexResetReview,
)
DIRECTORY = Path(__file__).resolve().parents[2] / "app" / "monitors"


def test_codex_models_are_registered_and_all_instants_are_timezone_aware() -> None:
    for model in MODELS:
        table = model.__table__
        assert metadata.tables[table.name] is table
        for column in table.columns:
            if isinstance(column.type, DateTime):
                assert column.type.timezone, (table.name, column.name)


def test_codex_services_only_import_own_orm_and_use_source_ai_contracts() -> None:
    for path in DIRECTORY.glob("codex_*.py"):
        imported = {
            node.module
            for node in ast.walk(ast.parse(path.read_text()))
            if isinstance(node, ast.ImportFrom) and node.module
        }
        assert not any(
            name.endswith("models") and not name.startswith("monitors.") for name in imported
        )
        assert not {"fastapi", "starlette", "httpx", "requests"} & imported
    schemas = ast.parse((DIRECTORY / "codex_schemas.py").read_text())
    assert not any(
        isinstance(node, ast.ImportFrom)
        and node.module
        and node.module.startswith(("sqlalchemy", "db", "monitors.codex_models"))
        for node in ast.walk(schemas)
    )
