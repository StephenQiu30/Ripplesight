from collections.abc import Iterator
from datetime import timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from tests.integration.test_editorial_source_profiles import job, setup
from tests.unit.test_editorial_rsshub import FEED, NOW, rsshub_config

from connections.editorial_rsshub import require_editorial_rsshub_execution_in_transaction
from connections.editorial_schemas import EditorialRsshubApprovalInput
from connections.editorial_services import EditorialSourceService
from connections.editorial_topic_sources import (
    list_editorial_topic_sources_in_transaction,
    require_editorial_topic_profiles_in_transaction,
)
from core.errors import ApplicationError
from jobs.schemas import BudgetPolicyInput, ComponentPolicyInput, CostClass
from jobs.services import ResourceBudgetService
from sources.editorial_factory import ConfiguredEditorialCollectorFactory
from sources.editorial_schemas import fingerprint


@pytest.fixture
def engine() -> Iterator[Engine]:
    import os

    url = os.getenv("HOTKEY_TEST_DATABASE_URL")
    if url is None:
        pytest.skip("isolated PostgreSQL is required")
    value = create_engine(url)
    try:
        yield value
    finally:
        value.dispose()


def configure(session):
    _, owner, existing, command = setup(session)
    config = rsshub_config()
    command = command.model_copy(
        update={
            "operation_id": uuid4(),
            "expected_revision": existing.revision,
            "enabled": False,
            "interval_minutes": 60,
            "configuration": config,
        }
    )
    service = EditorialSourceService(session, clock=lambda: NOW)
    profile = service.save_profile(owner_id=owner, profile_id=existing.id, command=command)
    return service, owner, profile, command


def approval(profile):
    return EditorialRsshubApprovalInput(
        operation_id=uuid4(),
        expected_revision=profile.revision,
        configuration_version=profile.configuration_version,
        configuration_sha256=fingerprint(profile.configuration.model_dump(mode="json")).hex(),
        reason="Controlled review of exact deployment egress and free finite feed",
        review=profile.configuration.rsshub.review,
    )


def enable(service, owner, profile, command):
    return service.save_profile(
        owner_id=owner,
        profile_id=profile.id,
        command=command.model_copy(
            update={"operation_id": uuid4(), "expected_revision": profile.revision, "enabled": True}
        ),
    )


def test_approval_is_independent_idempotent_cas_and_does_not_enable_or_upgrade_data_policy(engine):
    with Session(engine) as session:
        service, owner, profile, command = configure(session)
        with pytest.raises(ApplicationError, match="editorial_source_unavailable"):
            enable(service, owner, profile, command)
        session.rollback()
        review = approval(profile)
        with pytest.raises(ApplicationError, match="editorial_version_conflict"):
            service.approve_rsshub(
                owner_id=owner,
                profile_id=profile.id,
                command=review.model_copy(update={"configuration_sha256": "0" * 64}),
            )
        session.rollback()
        result = service.approve_rsshub(owner_id=owner, profile_id=profile.id, command=review)
        assert result.enabled is False
        assert (
            service.approve_rsshub(owner_id=owner, profile_id=profile.id, command=review) == result
        )
        with pytest.raises(ApplicationError, match="idempotency_conflict"):
            service.approve_rsshub(
                owner_id=owner,
                profile_id=profile.id,
                command=review.model_copy(update={"reason": "different operation input"}),
            )
        session.rollback()
        with session.begin():
            assert session.execute(
                text(
                    "SELECT status,enabled,policy_version FROM source_access_policies "
                    "WHERE owner_id=:owner"
                ),
                {"owner": owner},
            ).one() == ("approved", True, 1)
            assert (
                session.execute(
                    text("SELECT count(*) FROM resource_component_policies WHERE owner_id=:owner"),
                    {"owner": owner},
                ).scalar_one()
                == 1
            )
        current = enable(service, owner, profile, command)
        with session.begin():
            proof = require_editorial_rsshub_execution_in_transaction(
                session,
                owner_id=owner,
                profile_id=current.id,
                configuration_version=current.configuration_version,
                revision=current.revision,
                now=NOW,
            )
            assert proof.downstream_request_count is None and proof.supplier_fee_cny_micros == 0
            require_editorial_topic_profiles_in_transaction(
                session, owner_id=owner, profile_ids=(current.id,), now=NOW
            )
            rows = list_editorial_topic_sources_in_transaction(session, owner_id=owner, now=NOW)
            assert len(rows) == 1 and rows[0].selectable and rows[0].query_mode == "author_stream"
            assert not hasattr(rows[0], "route")


def test_runtime_rechecks_expiry_connection_source_policy_and_ownership_without_rollback(engine):
    with Session(engine) as session:
        service, owner, profile, command = configure(session)
        service.approve_rsshub(owner_id=owner, profile_id=profile.id, command=approval(profile))
        current = enable(service, owner, profile, command)

        def gate(*, now=NOW, selected_owner=owner):
            return require_editorial_rsshub_execution_in_transaction(
                session,
                owner_id=selected_owner,
                profile_id=current.id,
                configuration_version=current.configuration_version,
                revision=current.revision,
                now=now,
            )

        with session.begin():
            with pytest.raises(ApplicationError, match="editorial_source_unavailable"):
                gate(now=NOW + timedelta(days=7))
            assert session.in_transaction()
            with pytest.raises(ApplicationError, match="resource_not_found"):
                gate(selected_owner=uuid4())
            assert (
                list_editorial_topic_sources_in_transaction(session, owner_id=uuid4(), now=NOW)
                == ()
            )
            session.execute(
                text("UPDATE source_connections SET status='disabled' WHERE id=:id"),
                {"id": current.connection_id},
            )
            session.expire_all()
            with pytest.raises(ApplicationError, match="connection_disabled"):
                gate()
            rows = list_editorial_topic_sources_in_transaction(session, owner_id=owner, now=NOW)
            assert not rows[0].selectable and rows[0].reason == "connection_disabled"
        with session.begin():
            session.execute(
                text("UPDATE source_connections SET status='active' WHERE id=:id"),
                {"id": current.connection_id},
            )
            session.execute(
                text("UPDATE source_access_policies SET enabled=false WHERE owner_id=:owner"),
                {"owner": owner},
            )
            session.expire_all()
            rows = list_editorial_topic_sources_in_transaction(session, owner_id=owner, now=NOW)
            assert not rows[0].selectable and rows[0].reason == "source_policy_unavailable"


def test_factory_consumes_persisted_approval_and_existing_request_ledger(engine):
    with Session(engine) as session:
        service, owner, profile, command = configure(session)
        service.approve_rsshub(owner_id=owner, profile_id=profile.id, command=approval(profile))
        current = enable(service, owner, profile, command)
        accepted, operation = job(session, owner, current)
        prepared = service.begin_run(
            owner_id=owner,
            profile_id=current.id,
            operation_id=operation,
            job_id=accepted.id,
            configuration_version=current.configuration_version,
            revision=current.revision,
        )
        ResourceBudgetService(session, clock=lambda: NOW).save_component_policy(
            owner_id=owner,
            command=ComponentPolicyInput(
                component_key="collector.editorial",
                component_version="controlled-v1",
                cost_class=CostClass.ZERO_PRICE,
                enabled_for_core=True,
                terms_reference="test://existing-request-meter",
                reviewed_at=NOW,
            ),
        )
        ResourceBudgetService(session, clock=lambda: NOW).save_budget_policy(
            owner_id=owner,
            command=BudgetPolicyInput(
                budget_key="controlled.network",
                metric="network_request",
                scope_kind="global",
                limit_units=10,
                window_seconds=3600,
                window_anchor_at=NOW,
                enabled=True,
            ),
        )
    sent = []

    def response(request):
        sent.append(str(request.url))
        return httpx.Response(200, content=FEED)

    def gate(session, frozen):
        return require_editorial_rsshub_execution_in_transaction(
            session,
            owner_id=owner,
            profile_id=frozen.profile.id,
            configuration_version=frozen.profile.configuration_version,
            revision=frozen.profile.revision,
            now=NOW,
        )

    registry = ConfiguredEditorialCollectorFactory(
        sessionmaker(engine),
        owner_id=owner,
        job_id=accepted.id,
        operation_id=operation,
        public_enabled=True,
        rsshub_admission=gate,
        transport=httpx.MockTransport(response),
        clock=lambda: NOW,
    )(prepared)
    page = registry.collect(current, prepared.cursor, {})
    registry.close()
    assert page.status == "complete" and len(sent) == 1, page.reason
    with Session(engine) as session, session.begin():
        assert (
            session.execute(
                text("SELECT count(*) FROM resource_usage_attempts WHERE owner_id=:owner"),
                {"owner": owner},
            ).scalar_one()
            == 1
        )
        assert (
            session.execute(
                text(
                    "SELECT sum(actual_units) FROM resource_budget_reservations "
                    "WHERE owner_id=:owner AND metric='network_request'"
                ),
                {"owner": owner},
            ).scalar_one()
            == 1
        )
