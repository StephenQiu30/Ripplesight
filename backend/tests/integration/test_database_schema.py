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


def test_manual_skip_receipts_have_owner_version_and_jsonb_constraints(
    schema_engine: Engine,
) -> None:
    inspector = inspect(schema_engine)
    table = "monitor_topic_run_skips"
    assert inspector.get_pk_constraint(table)["constrained_columns"] == ["owner_id", "operation_id"]
    columns = {item["name"]: item for item in inspector.get_columns(table)}
    assert set(columns) == {
        "owner_id",
        "operation_id",
        "topic_id",
        "topic_version",
        "receipt",
        "recorded_at",
    }
    assert str(columns["receipt"]["type"]) == "JSONB" and not columns["receipt"]["nullable"]
    assert columns["recorded_at"]["type"].timezone is True
    checks = {item["name"]: item["sqltext"] for item in inspector.get_check_constraints(table)}
    assert "jsonb_typeof(receipt)" in checks["monitor_topic_run_skips_receipt_check"]
    foreign_keys = {item["name"]: item for item in inspector.get_foreign_keys(table)}
    assert foreign_keys["monitor_topic_run_skips_owner_topic_fkey"]["constrained_columns"] == [
        "owner_id",
        "topic_id",
    ]
    assert foreign_keys["monitor_topic_run_skips_version_fkey"]["constrained_columns"] == [
        "topic_id",
        "topic_version",
    ]
    assert all(item["options"]["ondelete"] == "CASCADE" for item in foreign_keys.values())


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


def test_topic_collection_version_columns_have_bounded_constraints(schema_engine: Engine) -> None:
    inspector = inspect(schema_engine)
    columns = {column["name"]: column for column in inspector.get_columns("monitor_topic_versions")}
    checks = {
        check["name"]: check["sqltext"]
        for check in inspector.get_check_constraints("monitor_topic_versions")
    }
    for key in (
        "search_language",
        "search_window_seconds",
        "max_queries",
        "max_items_per_query",
        "max_requests_per_query",
    ):
        assert columns[key]["nullable"] is False
        assert columns[key]["default"] is not None
        assert key in checks[f"monitor_topic_versions_{key}_check"]


def test_annotation_constraint_allows_missing_sentiment_for_valid_relevance(
    schema_engine: Engine,
) -> None:
    checks = inspect(schema_engine).get_check_constraints("content_annotations")
    check = next(
        item["sqltext"]
        for item in checks
        if item["name"] == "content_annotations_output_status_check"
    )
    assert "sentiment IS NOT NULL" not in check
    assert "sentiment IS NULL" in check
    assert "relevant" in check and "unanalyzed" in check and "relevance_reason" in check


def test_scheduled_query_plan_is_nullable_and_limited_to_skipped_search(
    schema_engine: Engine,
) -> None:
    inspector = inspect(schema_engine)
    columns = {column["name"]: column for column in inspector.get_columns("collection_due_windows")}
    assert columns["query_plan"]["nullable"] is True
    assert str(columns["query_plan"]["type"]) == "JSONB"
    checks = {
        item["name"]: item["sqltext"]
        for item in inspector.get_check_constraints("collection_due_windows")
    }
    check = checks["collection_due_windows_query_plan_check"]
    for fragment in (
        "query_plan IS NULL",
        "jsonb_typeof",
        "search",
        "skipped",
        "topic_id IS NOT NULL",
    ):
        assert fragment in check


def test_collection_execution_attribution_constraints(schema_engine: Engine) -> None:
    inspector = inspect(schema_engine)
    foreign_keys = inspector.get_foreign_keys("content_observations")
    attribution = next(
        item for item in foreign_keys if item["name"] == "content_observations_execution_fkey"
    )
    assert attribution["constrained_columns"] == ["job_id", "execution_epoch"]
    assert attribution["referred_table"] == "job_attempts"
    assert attribution["referred_columns"] == ["job_id", "lease_epoch"]
    attempt_checks = {item["name"] for item in inspector.get_check_constraints("job_attempts")}
    assert {
        "job_attempts_observed_count_check",
        "job_attempts_untracked_count_check",
    } <= attempt_checks
    observation_checks = {
        item["name"] for item in inspector.get_check_constraints("content_observations")
    }
    assert "content_observations_execution_epoch_check" in observation_checks


def test_comment_relation_constraint_preserves_unknown_parent(schema_engine: Engine) -> None:
    checks = inspect(schema_engine).get_check_constraints("content_threads")
    constraint = next(
        item["sqltext"] for item in checks if item["name"] == "content_threads_distinct_check"
    )
    assert "unresolved" in constraint
    assert "parent_content_id IS NULL" in constraint and "root_content_id IS NULL" in constraint
