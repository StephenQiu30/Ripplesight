"""Exercise finite recovery denial replay in owned PostgreSQL targets."""

import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from psycopg import sql
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session
from tests.integration.test_data_lifecycle import (
    LifecycleTestContext,
    _policy,
)
from tests.integration.test_data_lifecycle import (
    lifecycle_context as lifecycle_context,
)
from tests.integration.test_restore_isolation import EmptyEvidenceInspector
from tests.recovery_fixtures import recovery_sample
from tests.unit.test_backup_restore import _manifest

from backups.adapters.postgres import PostgresDumpAdapter
from backups.restore import BackupRestoreError, BackupRestoreService
from backups.services import BackupService
from evidence.journal_contract import verify_recovery_inputs
from evidence.models import DeletionDirective
from evidence.schemas import AccessPolicyStatus, DataClass, DeletionReason, RetentionPolicyInput
from evidence.services import (
    LifecycleService,
    RetentionPolicyService,
    SourceAccessPolicyService,
    readable_resource_ids_query,
)
from sources.contracts import SourceCapability

SCHEMA = Path(__file__).resolve().parents[2] / "sql" / "schema.sql"


def _track(context: LifecycleTestContext, owner: UUID, resource: UUID) -> None:
    now = datetime.now(UTC)
    with context.sessions() as session:
        access = SourceAccessPolicyService(session).save(
            owner_id=owner,
            command=_policy(
                status=AccessPolicyStatus.APPROVED,
                enabled=True,
                reviewed_at=now,
                review_expires_at=now + timedelta(days=30),
                field_purposes={"external_id": "controlled identity"},
            ),
        )
        RetentionPolicyService(session).save(
            owner_id=owner,
            command=RetentionPolicyInput(
                source_policy_id=access.id,
                data_class=DataClass.STRUCTURED,
                requested_days=30,
                source_max_days=30,
            ),
        )
        admission = SourceAccessPolicyService(session).admit_payload(
            owner_id=owner,
            source_key="douyin",
            capability=SourceCapability.SEARCH,
            data_class=DataClass.STRUCTURED,
            collected_at=now,
            payload={"external_id": str(resource)},
        )
        LifecycleService(session).track_resource(
            owner_id=owner,
            resource_type="content_item",
            resource_id=resource,
            admission=admission,
            cleanup_targets=[],
        )


def _inputs(tmp_path, manifest, targets, **kwargs):
    snapshot, checkpoint = recovery_sample(manifest, targets, **kwargs)
    path = tmp_path / "ledger.json"
    path.write_text(snapshot.model_dump_json())
    path.chmod(0o600)
    return (
        path,
        checkpoint,
        verify_recovery_inputs(
            snapshot_path=path, checkpoint_json=checkpoint.model_dump_json(), manifest=manifest
        ),
    )


def test_real_dump_replay_keeps_other_owner_and_denies_business_connection(
    lifecycle_context: LifecycleTestContext, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = lifecycle_context
    resource, operation = uuid4(), uuid4()
    _track(context, context.owner_id, resource)
    _track(context, context.other_owner_id, resource)
    source_url = context.engine.url
    candidate = BackupService(
        engine=context.engine,
        archive_writer=PostgresDumpAdapter(source_url.render_as_string(hide_password=False)),
        object_inspector=EmptyEvidenceInspector(),
        evidence_bucket="controlled-no-objects",
        schema_path=SCHEMA,
    ).create_candidate(tmp_path)
    path, checkpoint, _ = _inputs(
        tmp_path,
        candidate.manifest,
        [(context.owner_id, "content_item", resource)],
        operation_id=operation,
    )
    # The snapshot contains the resource, while the source now has a denial.
    with context.sessions() as session:
        LifecycleService(session).request_deletion(
            owner_id=context.owner_id,
            operation_id=operation,
            resource_type="content_item",
            resource_id=resource,
            reason=DeletionReason.AUTHORIZATION_REVOKED,
        )
    admin = create_engine(source_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    role = "hotkey_test_replay_" + uuid4().hex[:20]
    password = secrets.token_hex(24)
    created_role = False
    original = BackupRestoreService._replay_resources
    inspected = []

    def inspect(engine, recovery):
        name = engine.url.database
        assert name.startswith("hotkey_test_restore_")
        denied = create_engine(engine.url.set(username=role, password=password), pool_pre_ping=True)
        try:
            with pytest.raises(OperationalError) as failure, denied.connect():
                pass
            assert "does not have CONNECT privilege" in str(failure.value.orig)
        finally:
            denied.dispose()
        assert original(engine, recovery) == 1
        assert original(engine, recovery) == 1
        with Session(engine) as session:

            def readable(owner):
                return set(
                    session.scalars(
                        readable_resource_ids_query(
                            owner_id=owner, resource_type="content_item", now=datetime.now(UTC)
                        )
                    )
                )

            assert resource not in readable(context.owner_id)
            assert resource in readable(context.other_owner_id)
            rows = session.scalars(select(DeletionDirective)).all()
            assert len(rows) == 1 and rows[0].operation_id == operation
            assert rows[0].status == "pending" and rows[0].completed_at is None
        inspected.append(name)
        return 1

    service = BackupRestoreService(
        source_database_url=source_url,
        isolation_database_url=source_url.set(database="postgres"),
        schema_path=SCHEMA,
    )
    monkeypatch.setattr(service, "_replay_resources", inspect)
    try:
        with admin.connect() as connection:
            driver = connection.connection.driver_connection
            driver.execute(
                sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                    sql.Identifier(role), sql.Literal(password)
                )
            )
            created_role = True
            # Real SQL checks a separate ordinary source role and rejects the
            # actual maintenance role, without accessing any business database.
            role_check = BackupRestoreService(
                source_database_url=source_url.set(
                    database="controlled_source_identity", username=role
                ),
                isolation_database_url=source_url.set(database="postgres"),
                schema_path=SCHEMA,
            )
            role_check._check_replay_role(connection)
            role_check._source_url = source_url.set(
                database="controlled_source_identity",
                username=connection.scalar(text("SELECT current_user")),
            )
            with pytest.raises(BackupRestoreError, match="bypass"):
                role_check._check_replay_role(connection)
        result = service.verify_replay(
            candidate.directory, snapshot_path=path, checkpoint_json=checkpoint.model_dump_json()
        )
        assert result.replay_verified and result.replayed_sequence == 1
        assert result.ledger_id == checkpoint.ledger_id and result.matched_resources == 1
        assert result.service_open_permitted is False and result.evidence_objects_verified == 0
        assert len(inspected) == 1
        with admin.connect() as connection:
            assert (
                connection.scalar(
                    text("SELECT count(*) FROM pg_database WHERE datname=:name"),
                    {"name": inspected[0]},
                )
                == 0
            )
        with context.sessions() as session:
            assert session.scalar(select(func.count()).select_from(DeletionDirective)) == 1
    finally:
        try:
            if created_role:
                with admin.connect() as connection:
                    connection.exec_driver_sql(f'DROP ROLE "{role}"')
        finally:
            admin.dispose()


@pytest.mark.parametrize("failure", ["second_event", "commit"])
def test_batch_failure_rolls_back_every_denial(
    lifecycle_context: LifecycleTestContext,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    context = lifecycle_context
    resources = [uuid4(), uuid4()]
    for resource in resources:
        _track(context, context.owner_id, resource)
    _, _, recovery = _inputs(
        tmp_path,
        _manifest(),
        [(context.owner_id, "content_item", resource) for resource in resources],
    )
    original = LifecycleService.replay_denial_in_transaction
    calls = []

    def fail_event(service, **kwargs):
        matched = original(service, **kwargs)
        calls.append(matched)
        if len(calls) == 2:
            raise SQLAlchemyError("controlled failure after two staged denials")
        return matched

    def fail_commit(session):
        if session.bind is context.engine:
            assert session.scalar(select(func.count()).select_from(DeletionDirective)) == 2
            raise SQLAlchemyError("controlled replay commit failure")

    if failure == "second_event":
        monkeypatch.setattr(LifecycleService, "replay_denial_in_transaction", fail_event)
    else:
        event.listen(Session, "before_commit", fail_commit)
    try:
        with pytest.raises(SQLAlchemyError):
            BackupRestoreService._replay_resources(context.engine, recovery)
    finally:
        if failure == "commit":
            event.remove(Session, "before_commit", fail_commit)
    with context.sessions() as session:
        assert session.scalar(select(func.count()).select_from(DeletionDirective)) == 0
        assert set(
            session.scalars(
                readable_resource_ids_query(
                    owner_id=context.owner_id, resource_type="content_item", now=datetime.now(UTC)
                )
            )
        ) == set(resources)


def test_missing_resource_does_not_hide_existing_operation_conflict(
    lifecycle_context: LifecycleTestContext, tmp_path: Path
) -> None:
    context = lifecycle_context
    resource, operation = uuid4(), uuid4()
    _track(context, context.owner_id, resource)
    with context.sessions() as session:
        LifecycleService(session).request_deletion(
            owner_id=context.owner_id,
            operation_id=operation,
            resource_type="content_item",
            resource_id=resource,
            reason=DeletionReason.USER_REQUEST,
        )
    _, _, recovery = _inputs(
        tmp_path, _manifest(), [(context.owner_id, "content_item", uuid4())], operation_id=operation
    )
    with pytest.raises(BackupRestoreError, match="conflicts"):
        BackupRestoreService._replay_resources(context.engine, recovery)
    with context.sessions() as session:
        assert session.scalar(select(func.count()).select_from(DeletionDirective)) == 1


def test_absent_resource_is_idempotent_without_operation_conflict(
    lifecycle_context: LifecycleTestContext, tmp_path: Path
) -> None:
    _, _, recovery = _inputs(tmp_path, _manifest(), [(uuid4(), "content_item", uuid4())])
    assert BackupRestoreService._replay_resources(lifecycle_context.engine, recovery) == 0


def test_real_role_precheck_rejects_superuser_and_indirect_maintenance_membership(
    lifecycle_context: LifecycleTestContext,
) -> None:
    """All role mutations are temporary owned roles, never real service roles."""
    url = lifecycle_context.engine.url
    roles = {
        kind: "hotkey_test_" + kind + "_" + uuid4().hex[:16]
        for kind in ("plain", "maint", "middle", "business", "super")
    }
    created = []
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as connection:
            try:
                for kind, role in roles.items():
                    connection.exec_driver_sql(
                        f'CREATE ROLE "{role}" NOLOGIN' + (" SUPERUSER" if kind == "super" else "")
                    )
                    created.append(role)
                connection.exec_driver_sql(f'GRANT "{roles["maint"]}" TO "{roles["middle"]}"')
                connection.exec_driver_sql(f'GRANT "{roles["middle"]}" TO "{roles["business"]}"')
                connection.exec_driver_sql(f'SET ROLE "{roles["maint"]}"')
                for kind in ("plain", "maint", "business", "super"):
                    service = BackupRestoreService(
                        # Identity-only URL: never connected or used as a target.
                        source_database_url=url.set(
                            database="controlled_source_identity", username=roles[kind]
                        ),
                        isolation_database_url=url.set(database="postgres"),
                        schema_path=SCHEMA,
                    )
                    if kind == "plain":
                        service._check_replay_role(connection)
                    else:
                        with pytest.raises(BackupRestoreError, match="bypass"):
                            service._check_replay_role(connection)
            finally:
                connection.exec_driver_sql("RESET ROLE")
                for role in reversed(created):
                    connection.exec_driver_sql(f'DROP ROLE "{role}"')
    finally:
        admin.dispose()
