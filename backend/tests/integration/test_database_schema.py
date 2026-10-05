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

from ai.schemas import AiFailureCode
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


def test_ai_failure_constraint_covers_stable_output_truncation(schema_engine: Engine) -> None:
    checks = inspect(schema_engine).get_check_constraints("ai_calls")
    failure_check = next(check["sqltext"] for check in checks if "rate_limited" in check["sqltext"])
    assert set(re.findall(r"'([a-z_]+)'", failure_check)) == {code.value for code in AiFailureCode}


def test_editorial_topic_matches_have_frozen_owner_scoped_structure(schema_engine: Engine) -> None:
    inspector = inspect(schema_engine)
    assert "editorial_profile_ids" in {
        column["name"] for column in inspector.get_columns("monitor_topic_versions")
    }
    assert "content_topic_matches" in inspector.get_table_names(schema="public")
    columns = {column["name"] for column in inspector.get_columns("content_topic_matches")}
    assert {
        "owner_id",
        "topic_id",
        "topic_rule_version",
        "content_id",
        "content_version_id",
        "profile_id",
        "profile_configuration_version",
        "observation_id",
        "job_id",
        "connection_id",
        "connection_version",
        "policy_version",
        "matched_at",
    }.issubset(columns)
    foreign_keys = inspector.get_foreign_keys("content_topic_matches")
    assert any(
        item["constrained_columns"] == ["owner_id", "content_id", "content_version_id"]
        for item in foreign_keys
    )
    assert any(item["constrained_columns"] == ["owner_id", "topic_id"] for item in foreign_keys)
    assert inspector.get_pk_constraint("content_version_inputs")["constrained_columns"] == [
        "owner_id",
        "content_version_id",
        "observation_id",
    ]
    dependencies = inspector.get_foreign_keys("content_version_inputs")
    assert any(
        item["constrained_columns"] == ["owner_id", "observation_id"]
        and item["options"].get("ondelete") == "RESTRICT"
        for item in dependencies
    )


def test_export_cancellation_preserves_owner_fkeys_and_partial_result_dedup(schema_engine):
    inspector = inspect(schema_engine)
    for table, index_name, columns in (
        (
            "report_exports",
            "report_exports_result_key",
            ["owner_id", "report_id", "report_version", "format", "renderer_version"],
        ),
        (
            "content_export_requests",
            "content_exports_result_key",
            ["owner_id", "input_hash", "format", "renderer_version", "schema_version"],
        ),
    ):
        reflected = next(
            index for index in inspector.get_indexes(table) if index["name"] == index_name
        )
        assert reflected["unique"] is True and reflected["column_names"] == columns
        assert "cancelled" in str(reflected.get("dialect_options", {}).get("postgresql_where", ""))
        assert not reflected.get("duplicates_constraint")
        assert any(
            "cancelled" in check["sqltext"] for check in inspector.get_check_constraints(table)
        )
        assert any(
            fk["constrained_columns"] == ["owner_id", "job_id"] and fk["referred_table"] == "jobs"
            for fk in inspector.get_foreign_keys(table)
        )
    assert any(
        fk["constrained_columns"] == ["owner_id", "report_id"]
        and fk["referred_columns"] == ["owner_id", "id"]
        for fk in inspector.get_foreign_keys("report_exports")
    )
