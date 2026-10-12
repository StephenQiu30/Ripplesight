"""Exercise disposable restore targets using only owned PostgreSQL test databases."""

import os
import re
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine, event, func, select, text
from sqlalchemy.engine import make_url
from tests.conftest import validate_test_database_url

from backups import restore
from backups.adapters.postgres import BackupToolError, PostgresDumpAdapter
from backups.schemas import EvidenceObjectMetadata
from backups.services import BackupService
from db.metadata import metadata


class EmptyEvidenceInspector:
    """Refuse object-store I/O; these fresh fixtures contain no evidence objects."""

    def stat(self, object_name: str) -> EvidenceObjectMetadata | None:
        raise AssertionError(f"unexpected evidence object: {object_name}")


@pytest.mark.parametrize("failure", [None, "restore", "reconcile"])
def test_real_restore_targets_use_test_names_and_are_removed_on_every_outcome(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str | None
) -> None:
    value = os.getenv("HOTKEY_TEST_DATABASE_URL")
    if value is None:
        pytest.skip("isolated PostgreSQL test database is required")
    validate_test_database_url(value)
    source_url = make_url(value)
    source = create_engine(source_url)
    admin = create_engine(source_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    created: list[str] = []

    def guard_create(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.startswith("CREATE DATABASE"):
            assert re.fullmatch(
                r'CREATE DATABASE "hotkey_test_restore_[a-f0-9]{32}" WITH ALLOW_CONNECTIONS false',
                statement,
            )

    def record_create(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.startswith("CREATE DATABASE"):
            created.append(statement.split('"')[1])

    event.listen(Engine, "before_cursor_execute", guard_create)
    event.listen(Engine, "after_cursor_execute", record_create)
    try:
        candidate = BackupService(
            engine=source,
            archive_writer=PostgresDumpAdapter(value),
            object_inspector=EmptyEvidenceInspector(),
            evidence_bucket="controlled-no-evidence",
            schema_path=Path(__file__).resolve().parents[2] / "sql" / "schema.sql",
        ).create_candidate(tmp_path)
        assert candidate.manifest.evidence_objects == ()
        service = restore.BackupRestoreService(
            source_database_url=source_url,
            isolation_database_url=source_url.set(database="postgres"),
            schema_path=Path(__file__).resolve().parents[2] / "sql" / "schema.sql",
        )
        if failure == "restore":

            def fail_restore(_adapter, _archive):
                raise BackupToolError("controlled failure after target creation")

            monkeypatch.setattr(PostgresDumpAdapter, "restore_archive", fail_restore)
        elif failure == "reconcile":

            def fail_reconcile(_engine, _manifest):
                raise restore.BackupRestoreError("controlled reconciliation failure")

            monkeypatch.setattr(service, "_check_restored_data", fail_reconcile)
        if failure is None:
            result = service.verify(candidate.directory)
            assert result.database_restored and result.table_count == len(metadata.tables)
            assert result.evidence_objects_verified == 0
        else:
            with pytest.raises(restore.BackupRestoreError):
                service.verify(candidate.directory)
        assert len(created) == 1
        with admin.connect() as connection:
            assert (
                connection.scalar(
                    text("SELECT count(*) FROM pg_database WHERE datname=ANY(:names)"),
                    {"names": created},
                )
                == 0
            )
        with source.connect() as connection:
            assert {
                item.name: connection.scalar(
                    select(func.count()).select_from(metadata.tables[item.name])
                )
                for item in candidate.manifest.database.tables
            } == {item.name: item.row_count for item in candidate.manifest.database.tables}
    finally:
        event.remove(Engine, "before_cursor_execute", guard_create)
        event.remove(Engine, "after_cursor_execute", record_create)
        source.dispose()
        try:
            # If a regression leaves a target behind, the failed test still owns
            # and removes only names whose CREATE actually succeeded above.
            with admin.connect() as connection:
                for name in created:
                    if connection.scalar(
                        text("SELECT 1 FROM pg_database WHERE datname=:name"), {"name": name}
                    ):
                        connection.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')
                    assert (
                        connection.scalar(
                            text("SELECT 1 FROM pg_database WHERE datname=:name"), {"name": name}
                        )
                        is None
                    )
        finally:
            admin.dispose()
