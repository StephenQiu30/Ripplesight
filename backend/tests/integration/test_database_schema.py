from __future__ import annotations

import os
import re
from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import Engine, Float, create_engine, inspect
from sqlalchemy.engine import Dialect
from sqlalchemy.sql.type_api import TypeEngine
from tests.conftest import validate_test_database_url

from db.metadata import metadata


@pytest.fixture
def schema_engine() -> Iterator[Engine]:
    database_url = os.getenv("HOTKEY_TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("HOTKEY_TEST_DATABASE_URL is required for PostgreSQL integration tests")
    validate_test_database_url(database_url)
    engine = create_engine(database_url)
    try:
        yield engine
    finally:
        engine.dispose()


def _postgresql_type(column_type: TypeEngine[Any], dialect: Dialect) -> str:
    compiled = " ".join(column_type.compile(dialect=dialect).upper().split())
    compiled = compiled.replace("TIMESTAMPTZ", "TIMESTAMP WITH TIME ZONE")
    compiled = compiled.replace("CHARACTER VARYING", "VARCHAR")
    if isinstance(column_type, Float) and compiled.startswith("FLOAT"):
        # PostgreSQL FLOAT defaults to float8; precision <= 24 selects float4.
        return (
            "REAL"
            if column_type.precision is not None and column_type.precision <= 24
            else ("DOUBLE PRECISION")
        )
    return re.sub(r"\s*([(),])\s*", r"\1", compiled)


def test_canonical_schema_matches_all_runtime_tables(schema_engine: Engine) -> None:
    inspector = inspect(schema_engine)
    database_tables = set(inspector.get_table_names(schema="public"))
    model_tables = set(metadata.tables)
    assert database_tables == model_tables, {
        "database_only": sorted(database_tables - model_tables),
        "model_only": sorted(model_tables - database_tables),
    }

    database_columns = inspector.get_multi_columns(schema="public")
    database_primary_keys = inspector.get_multi_pk_constraint(schema="public")
    for table_name, table in sorted(metadata.tables.items()):
        columns = {column["name"]: column for column in database_columns[("public", table_name)]}
        assert set(columns) == set(table.columns.keys()), table_name
        for column in table.columns:
            reflected = columns[column.name]
            column_name = f"{table_name}.{column.name}"
            assert _postgresql_type(reflected["type"], schema_engine.dialect) == _postgresql_type(
                column.type, schema_engine.dialect
            ), f"{column_name}: PostgreSQL type differs from its runtime mapping"
            assert reflected["nullable"] == column.nullable, (
                f"{column_name}: nullability differs from its runtime mapping"
            )
        assert database_primary_keys[("public", table_name)]["constrained_columns"] == [
            column.name for column in table.primary_key.columns
        ], f"{table_name}: primary key differs from its runtime mapping"
