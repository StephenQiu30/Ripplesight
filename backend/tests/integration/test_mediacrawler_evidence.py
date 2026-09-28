"""MediaCrawler version evidence is frozen on each accepted Bilibili job."""

from __future__ import annotations

import os
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from connections.presets import BILIBILI_PRESET
from connections.services import SourcePresetService
from jobs.execution import JobExecutionFailure, JobExecutionService, MessageReference
from jobs.models import Job, ResourceComponentPolicy
from jobs.schemas import JobAcceptanceInput, JobFailureCategory, JobObservationContext
from jobs.services import JobService, load_job_execution_configuration
from sources.adapters.mediacrawler import ADAPTER_VERSION
from sources.contracts import SourceCapability


def _command(connection_id: str, connection_version: int) -> JobAcceptanceInput:
    return JobAcceptanceInput(
        operation_id=uuid4(),
        kind="keyword.search",
        observation=JobObservationContext(
            configuration_ref="source:bilibili",
            configuration_version=connection_version,
            source_key="bilibili",
            source_capability=SourceCapability.SEARCH,
        ),
        scope={"connection_id": connection_id, "connection_version": connection_version},
    )


def test_bilibili_versions_survive_policy_change_and_failed_job() -> None:
    database_url = os.getenv("HOTKEY_TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("HOTKEY_TEST_DATABASE_URL is required for PostgreSQL integration tests")
    engine = create_engine(database_url)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    owner_id = uuid4()
    now = datetime.now(UTC)
    try:
        with engine.begin() as connection:
            connection.execute(text("TRUNCATE identity_users CASCADE"))
            connection.execute(
                text(
                    "INSERT INTO identity_users "
                    "(id, username, password_hash, credential_version, created_at, updated_at) "
                    "VALUES (:id, :name, 'test-only-hash', 1, :now, :now)"
                ),
                {"id": owner_id, "name": f"evidence-{owner_id}", "now": now},
            )

        with sessions.begin() as session:
            first_connection = SourcePresetService(session).apply_in_transaction(
                owner_id=owner_id, preset=BILIBILI_PRESET
            )
            policy = session.scalar(
                select(ResourceComponentPolicy).where(
                    ResourceComponentPolicy.owner_id == owner_id,
                    ResourceComponentPolicy.component_key == "collector.bilibili",
                )
            )
            assert policy is not None
            assert policy.upstream_revision == "380b426000aac3d612837ed72c99808347dc94c9"
            assert policy.patched_revision == "fb4e6c57ade1c7a2b3a61e69abc4fd4130047eb2"
            assert policy.component_version == ADAPTER_VERSION

        first_command = _command(
            str(first_connection.connection_id), first_connection.connection_version
        )
        with sessions() as session:
            first = JobService(session).accept(
                owner_id=owner_id,
                command=first_command,
            )

        changed = replace(
            BILIBILI_PRESET,
            component_version="mediacrawler-next-hotkey-safe",
            upstream_revision="1" * 40,
            patched_revision="2" * 40,
        )
        with sessions.begin() as session:
            second_connection = SourcePresetService(session).apply_in_transaction(
                owner_id=owner_id, preset=changed
            )
            second = JobService(session).accept_in_transaction(
                owner_id=owner_id,
                command=_command(
                    str(second_connection.connection_id), second_connection.connection_version
                ),
            )
        assert second_connection.connection_version > first_connection.connection_version
        with sessions() as session:
            repeated = JobService(session).accept(owner_id=owner_id, command=first_command)
        assert repeated.id == first.id

        with sessions() as session:
            execution = JobExecutionService(session, lease_seconds=30)
            lease = execution.acquire(job_id=first.id, worker_id="version-evidence-test")
            execution.record_failure(
                lease,
                message=MessageReference(
                    message_id=uuid4(), topic="job.accepted.v2", partition=0, offset=1
                ),
                failure=JobExecutionFailure(
                    error_code="mediacrawler_revision_mismatch",
                    category=JobFailureCategory.CONFIGURATION_UNAVAILABLE,
                    occurred_at=datetime.now(UTC),
                    next_action="核对固定采集工作树后重新提交",
                ),
            )

        with sessions() as session:
            old = session.get(Job, first.id)
            new = session.get(Job, second.id)
            assert old is not None and new is not None
            assert old.scope["connection_id"] == str(first_connection.connection_id)
            assert old.scope["connection_version"] == first_connection.connection_version
            assert old.upstream_revision == "380b426000aac3d612837ed72c99808347dc94c9"
            assert old.patched_revision == "fb4e6c57ade1c7a2b3a61e69abc4fd4130047eb2"
            assert old.adapter_version == ADAPTER_VERSION
            assert old.status == "failed"
            assert old.last_error_code == "mediacrawler_revision_mismatch"
            assert new.upstream_revision == "1" * 40
            assert new.patched_revision == "2" * 40
            assert new.adapter_version == "mediacrawler-next-hotkey-safe"
            assert new.scope["connection_version"] == second_connection.connection_version
            with (
                pytest.raises(IntegrityError, match="jobs_mediacrawler_version_evidence_check"),
                session.begin_nested(),
            ):
                session.execute(
                    text("UPDATE jobs SET patched_revision = NULL WHERE id = :id"),
                    {"id": second.id},
                )
            with (
                pytest.raises(
                    IntegrityError, match="resource_component_policies_revision_pair_check"
                ),
                session.begin_nested(),
            ):
                session.execute(
                    text(
                        "UPDATE resource_component_policies SET patched_revision = NULL "
                        "WHERE owner_id = :owner AND component_key = 'collector.bilibili'"
                    ),
                    {"owner": owner_id},
                )
        with sessions.begin() as session:
            session.execute(
                delete(ResourceComponentPolicy).where(
                    ResourceComponentPolicy.owner_id == owner_id,
                    ResourceComponentPolicy.component_key == "collector.bilibili",
                )
            )
        with sessions() as session:
            incomplete = JobService(session).accept(
                owner_id=owner_id,
                command=_command(
                    str(second_connection.connection_id), second_connection.connection_version
                ),
            )
            snapshot = load_job_execution_configuration(session, job_id=incomplete.id)
            assert snapshot is not None
            assert snapshot.upstream_revision is None
            assert snapshot.patched_revision is None
            assert snapshot.adapter_version is None
    finally:
        with engine.begin() as connection:
            connection.execute(text("TRUNCATE identity_users CASCADE"))
        engine.dispose()
