from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from api.router import api_router
from core.errors import ERROR_CATEGORIES, ApplicationError

BACKEND = Path(__file__).resolve().parents[2]
APP = BACKEND / "app"
REPOSITORY = BACKEND.parent
REGISTERED_PACKAGES = {
    "ai",
    "analysis",
    "api",
    "backups",
    "cli",
    "connections",
    "content",
    "core",
    "db",
    "events",
    "evidence",
    "jobs",
    "identity",
    "knowledge",
    "leaderboard",
    "monitors",
    "notifications",
    "operations",
    "publication",
    "reports",
    "sources",
    "worker",
}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _sql_files(root: Path) -> set[Path]:
    generated_directories = {
        ".git",
        ".mypy_cache",
        ".next",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "node_modules",
    }
    files: set[Path] = set()
    for directory, subdirectories, filenames in root.walk():
        subdirectories[:] = [name for name in subdirectories if name not in generated_directories]
        files.update(directory / name for name in filenames if Path(name).suffix.lower() == ".sql")
    return files


def _orm_ddl_calls(source: str) -> set[str]:
    forbidden_calls = {
        "create_all",
        "drop_all",
        "CreateTable",
        "DropTable",
        "CreateIndex",
        "DropIndex",
        "CreateSchema",
        "DropSchema",
        "AddConstraint",
        "DropConstraint",
        "CreateSequence",
        "DropSequence",
        "DDL",
    }
    tree = ast.parse(source)
    aliases = {
        alias.asname or alias.name: alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("sqlalchemy")
        for alias in node.names
    }

    def call_name(node: ast.expr) -> str:
        if isinstance(node, ast.Attribute):
            return node.attr
        if isinstance(node, ast.Name):
            return aliases.get(node.id, node.id)
        return ""

    schema_objects: set[str] = set()

    def is_schema_object(node: ast.expr) -> bool:
        return (
            (isinstance(node, ast.Name) and node.id in schema_objects)
            or (isinstance(node, ast.Attribute) and node.attr == "__table__")
            or (
                isinstance(node, ast.Subscript)
                and isinstance(node.value, ast.Attribute)
                and node.value.attr == "tables"
            )
            or (
                isinstance(node, ast.Call)
                and call_name(node.func) in {"Table", "Index", "MetaData"}
            )
        )

    # Follow local aliases of SQLAlchemy table/index/metadata objects.
    assignments = [node for node in ast.walk(tree) if isinstance(node, ast.Assign)]
    for _ in range(len(assignments) + 1):
        previous = schema_objects.copy()
        for assignment in assignments:
            if is_schema_object(assignment.value):
                schema_objects.update(
                    target.id for target in assignment.targets if isinstance(target, ast.Name)
                )
        if schema_objects == previous:
            break

    calls: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = call_name(node.func)
        if name in forbidden_calls:
            calls.add(name)
        if (
            name in {"create", "drop"}
            and isinstance(node.func, ast.Attribute)
            and is_schema_object(node.func.value)
        ):
            calls.add(name)
        if name in {"text", "execute", "exec_driver_sql"} and node.args:
            argument = node.args[0]
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                query = argument.value
            elif isinstance(argument, ast.JoinedStr):
                query = " ".join(
                    item.value
                    for item in argument.values
                    if isinstance(item, ast.Constant) and isinstance(item.value, str)
                )
            else:
                continue
            if re.search(
                r"\b(?:CREATE(?:\s+OR\s+REPLACE)?(?:\s+UNIQUE)?|ALTER|DROP)\s+"
                r"(?:TABLE|INDEX|SCHEMA|EXTENSION|FUNCTION|TRIGGER|TYPE|VIEW|SEQUENCE)\b",
                query,
                re.IGNORECASE,
            ):
                calls.add("inline DDL")
    return calls


def test_backend_has_no_wrapper_package() -> None:
    assert not (BACKEND / "src").exists()
    assert not (APP / "src").exists()
    assert not (APP / "app").exists()
    assert not (APP / "hotkey").exists()
    assert not any(path.name.startswith("v") and path.name[1:].isdigit() for path in APP.rglob("*"))


def test_backend_has_no_empty_top_level_package_placeholders() -> None:
    for package in APP.iterdir():
        if not package.is_dir() or package.name == "__pycache__":
            continue
        implementation_files = [
            path
            for path in package.rglob("*.py")
            if path.name != "__init__.py" and "__pycache__" not in path.parts
        ]
        assert implementation_files, package


def test_all_implemented_packages_are_registered() -> None:
    actual = {path.name for path in APP.iterdir() if path.is_dir() and path.name != "__pycache__"}
    assert actual == REGISTERED_PACKAGES


def test_events_service_reads_cross_domain_facts_through_dtos() -> None:
    imports = _imports(APP / "events" / "services.py")
    assert not {"analysis.models", "content.models", "monitors.models"} & imports


def test_public_api_uses_the_single_stable_namespace() -> None:
    assert api_router.prefix == "/api"


def test_schema_sql_is_the_only_ddl_source() -> None:
    assert _sql_files(REPOSITORY) == {BACKEND / "database" / "schema.sql"}
    assert not (BACKEND / "alembic.ini").exists()
    assert not (BACKEND / "migrations").exists()
    assert "alembic" not in (BACKEND / "pyproject.toml").read_text().lower()


def test_schema_is_a_complete_definition_without_merge_fragments() -> None:
    source = (BACKEND / "database" / "schema.sql").read_text().lower()
    comments = "\n".join(line for line in source.splitlines() if line.lstrip().startswith("--"))
    for marker in (
        "merge-only fragment",
        "integration fragment",
        "review fragment",
        "draft for root",
        "generated from",
        "parent merges",
        "root merges",
    ):
        assert marker not in comments, marker


def test_ddl_boundary_rejects_an_additional_sql_file(tmp_path: Path) -> None:
    schema = tmp_path / "backend" / "database" / "schema.sql"
    schema.parent.mkdir(parents=True)
    schema.touch()
    extra = tmp_path / "backend" / "database" / "patch.sql"
    extra.touch()
    assert _sql_files(tmp_path) - {schema} == {extra}


@pytest.mark.parametrize(
    "source",
    [
        "Base.metadata.create_all(engine)",
        "Base.metadata.drop_all(engine)",
        "CreateTable(Account.__table__)",
        "sqlalchemy.schema.CreateIndex(index)",
        "from sqlalchemy.schema import CreateTable as CT\nCT(Account.__table__)",
        "DDL('CREATE TABLE unexpected (id integer)')",
        "connection.exec_driver_sql('CREATE TABLE unexpected (id integer)')",
        "connection.execute(text('ALTER TABLE accounts ADD COLUMN other integer'))",
        "Account.__table__.create(engine)",
        "table = Table('accounts', metadata)\nalias = table\nalias.create(engine)",
        "index = Index('accounts_id', column)\nindex.create(engine)",
        "connection.exec_driver_sql('CREATE UNIQUE INDEX rogue ON accounts (id)')",
        "connection.exec_driver_sql('CREATE SEQUENCE rogue')",
        "CreateSequence(sequence)",
    ],
)
def test_ddl_boundary_rejects_orm_schema_creation(source: str) -> None:
    assert _orm_ddl_calls(source)


def test_every_persistent_domain_registers_its_models() -> None:
    model_modules = {f"{path.parent.name}.{path.stem}" for path in APP.glob("*/*models.py")}
    registered_modules = _imports(APP / "db" / "metadata.py")
    assert model_modules <= registered_modules


def test_application_and_tests_do_not_create_or_drop_schema() -> None:
    for directory in (APP, BACKEND / "tests"):
        for path in directory.rglob("*.py"):
            assert not _orm_ddl_calls(path.read_text()), path


def test_routers_do_not_import_persistence_or_service_implementations() -> None:
    for path in (APP / "api" / "routers").glob("*.py"):
        imports = _imports(path)
        assert not any(name.startswith("sqlalchemy") for name in imports)
        assert not any(name.endswith((".models", "_models")) for name in imports)
        assert not any(name.endswith((".services", "_services")) for name in imports)


def test_schema_modules_do_not_depend_on_http_or_orm() -> None:
    for path in APP.rglob("*schemas.py"):
        imports = _imports(path)
        assert not any(name.startswith(("fastapi", "starlette", "sqlalchemy")) for name in imports)


def test_content_service_uses_cross_domain_contracts_not_models() -> None:
    imports = _imports(APP / "content" / "services.py")
    foreign_models = {
        name for name in imports if name.endswith(".models") and name != "content.models"
    }

    assert foreign_models == set()


def test_source_contracts_do_not_depend_on_runtime_or_business_domains() -> None:
    imports = _imports(APP / "sources" / "contracts.py")
    forbidden = (
        "api",
        "db",
        "evidence",
        "jobs",
        "worker",
        "fastapi",
        "httpx",
        "sqlalchemy",
        "starlette",
    )

    assert not any(
        name == prefix or name.startswith(f"{prefix}.") for name in imports for prefix in forbidden
    )


def test_source_adapters_do_not_import_business_or_runtime_layers() -> None:
    forbidden = {
        "api",
        "db",
        "jobs",
        "worker",
        "cli",
        "content",
        "connections",
        "evidence",
        "sqlalchemy",
        "fastapi",
    }
    for path in (APP / "sources" / "adapters").rglob("*.py"):
        assert not {name.split(".")[0] for name in _imports(path)} & forbidden, path


def test_ai_adapters_do_not_import_business_or_runtime_layers() -> None:
    adapters = sorted((APP / "ai" / "adapters").glob("*.py"))
    assert APP / "ai" / "adapters" / "codex_app_server.py" in adapters
    forbidden = {
        "api",
        "worker",
        "cli",
        "jobs",
        "content",
        "monitors",
        "connections",
        "evidence",
        "sqlalchemy",
        "fastapi",
    }
    for path in adapters:
        assert not {name.split(".")[0] for name in _imports(path)} & forbidden, path


def test_identity_adapters_keep_external_verification_separate_from_persistence() -> None:
    adapters = sorted((APP / "identity" / "adapters").glob("*.py"))
    assert {path.name for path in adapters} == {
        "__init__.py",
        "email.py",
        "github.py",
        "verification_store.py",
    }
    forbidden = {"api", "db", "worker", "cli", "sqlalchemy", "fastapi", "starlette"}
    for path in adapters:
        imports = _imports(path)
        assert not {name.split(".")[0] for name in imports} & forbidden, path
        assert not {"identity.models", "identity.services", "core.config"} & imports, path


def test_analysis_reads_content_through_domain_contracts() -> None:
    imports = _imports(APP / "analysis" / "services.py")

    assert "content.models" not in imports
    assert "monitors.models" not in imports


def test_application_errors_are_registered_without_http_status() -> None:
    error = ApplicationError(next(iter(ERROR_CATEGORIES)))

    assert error.code in ERROR_CATEGORIES
    assert not hasattr(error, "status_code")
    assert not hasattr(error, "message")
    assert not any(
        name.startswith(("fastapi", "starlette")) for name in _imports(APP / "core" / "errors.py")
    )


def test_worker_does_not_depend_on_http_protocol() -> None:
    for path in (APP / "worker").glob("*.py"):
        assert not any(name.startswith(("fastapi", "starlette")) for name in _imports(path))


def test_all_literal_application_errors_are_registered() -> None:
    for path in APP.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in {"ApplicationError", "DependencyUnavailableError"}
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                assert node.args[0].value in ERROR_CATEGORIES, (
                    path,
                    node.lineno,
                    node.args[0].value,
                )


def test_resource_routes_declare_openapi_contract_fields() -> None:
    http_methods = {"get", "post", "put", "patch", "delete", "options", "head", "trace"}
    for path in (APP / "api" / "routers").glob("*.py"):
        tree = ast.parse(path.read_text())
        for function in ast.walk(tree):
            if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for node in function.decorator_list:
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                    continue
                if node.func.attr not in http_methods:
                    continue
                keyword_names = {
                    keyword.arg for keyword in node.keywords if keyword.arg is not None
                }
                assert {"operation_id", "response_model", "status_code"} <= keyword_names, path


def test_resource_routers_declare_openapi_tags() -> None:
    for path in (APP / "api" / "routers").glob("*.py"):
        if path.name == "__init__.py":
            continue
        tree = ast.parse(path.read_text())
        router_calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "APIRouter"
        ]
        assert router_calls, path
        assert all(
            any(keyword.arg == "tags" for keyword in call.keywords) for call in router_calls
        ), path
