from __future__ import annotations

import json
import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import Engine, create_engine, select, text
from sqlalchemy.orm import Session

from connections.editorial_models import (
    EditorialSourceMaterialReceipt,
    EditorialSourceProfile,
    EditorialSourceRun,
)
from connections.editorial_schemas import (
    EditorialProfileInput,
    EditorialRunReviewInput,
    ExternalEditorialInput,
)
from connections.editorial_services import (
    EditorialSourceService,
    capability_for,
    list_due_editorial_sources_in_transaction,
)
from content.models import ContentRecord
from core.errors import ApplicationError
from evidence.services import SourceAccessUnavailableError
from jobs.schemas import JobAcceptanceInput, JobObservationContext
from jobs.services import JobService
from sources.editorial_schemas import EditorialCursor, EditorialMaterial, EditorialPage

NOW = datetime(2026, 10, 2, 2, tzinfo=UTC)


@pytest.fixture
def engine() -> Iterator[Engine]:
    url = os.getenv("HOTKEY_TEST_DATABASE_URL")
    if url is None:
        pytest.skip("isolated PostgreSQL is required")
    value = create_engine(url)
    try:
        yield value
    finally:
        value.dispose()


def setup(
    session: Session,
    *,
    kind: str = "rss",
    personal: bool = False,
    external_token: bool = False,
    owner_id: UUID | None = None,
    configuration: dict | None = None,
):
    owner = owner_id or uuid4()
    config = {"kind": kind}
    if kind == "rss":
        config.update(feed_url="https://example.com/feed", allowed_hosts=("example.com",))
    config.update(configuration or {})
    command = EditorialProfileInput.model_validate(
        dict(
            operation_id=uuid4(),
            name="Controlled source",
            reason="Controlled source setup",
            policy_version=1,
            configuration=config,
        )
    )
    service = EditorialSourceService(session, clock=lambda: NOW)
    profile = service.save_profile(owner_id=owner, command=command, personal=personal)
    policy = uuid4()
    fields = {
        k: "Controlled evidence purpose"
        for k in (
            "object_type",
            "external_id",
            "identity_basis",
            "canonical_url",
            "author_name",
            "published_at",
            "text_scope",
            "text_origin",
            "title",
            "body",
        )
    }
    with session.begin():
        session.execute(
            text(
                "INSERT INTO source_access_policies (id,owner_id,source_key,capabi"
                "lity,status,enabled,access_basis,terms_reference,component_name,c"
                "omponent_version,component_license,processing_purpose,field_purpo"
                "ses,reviewed_at,policy_version,created_at,updated_at) VALUES (:id"
                ",:owner,:key,:cap,'approved',true,'manual_import','https://exampl"
                "e.com/terms','editorial-source','aihot-035f7b7f-v1','MIT','Contro"
                "lled source migration',CAST(:fields AS jsonb),:now,1,:now,:now)"
            ),
            dict(
                id=policy,
                owner=owner,
                key=profile.source_key,
                cap=capability_for(kind).value,
                fields=json.dumps(fields),
                now=NOW,
            ),
        )
        session.execute(
            text(
                "INSERT INTO evidence_retention_policies (id,owner_id,source_polic"
                "y_id,source_policy_version,data_class,requested_days,effective_da"
                "ys,policy_version,created_at,updated_at) VALUES (:id,:owner,:poli"
                "cy,1,'structured',30,30,1,:now,:now)"
            ),
            dict(id=uuid4(), owner=owner, policy=policy, now=NOW),
        )
    command = command.model_copy(
        update=dict(operation_id=uuid4(), expected_revision=1, enabled=True)
    )
    profile = service.save_profile(
        owner_id=owner, profile_id=profile.id, command=command, personal=personal
    )
    if external_token:
        service = EditorialSourceService(
            session, clock=lambda: NOW, external_tokens={profile.id: SecretStr("controlled-token")}
        )
    return service, owner, profile, command


def job(session: Session, owner: UUID, profile, *, operation: UUID | None = None):
    op = operation or uuid4()
    result = JobService(session, clock=lambda: NOW).accept(
        owner_id=owner,
        command=JobAcceptanceInput(
            operation_id=op,
            kind="source.editorial.poll",
            observation=JobObservationContext(
                configuration_ref=f"editorial-source:{profile.id}",
                configuration_version=profile.configuration_version,
                source_key=profile.source_key,
                source_capability=capability_for(profile.configuration.kind),
            ),
            scope={"profile_id": str(profile.id), "revision": profile.revision},
        ),
    )
    return result, op


def material(title="New model", **kw):
    return EditorialMaterial(
        url="https://example.com/post",
        identity_key="url:https://example.com/post",
        title=title,
        body_text="Full controlled original source content",
        body_status="ok",
        published_at=NOW - timedelta(hours=1),
        **kw,
    )


def begin(service, owner, profile, j, op):
    return service.begin_run(
        owner_id=owner,
        profile_id=profile.id,
        configuration_version=profile.configuration_version,
        revision=profile.revision,
        job_id=j.id,
        operation_id=op,
    )


def page(*rows, status="complete", reason=None):
    return EditorialPage(
        status=status,
        reason=reason,
        materials=rows,
        cursor=EditorialCursor(initialized_at=NOW, last_ok_at=NOW),
        observed_at=NOW,
    )


def test_profile_source_gate_version_idempotence_partition_and_read_only(engine):
    with Session(engine, expire_on_commit=False) as s:
        service, owner, p, cmd = setup(s)
        replay = service.save_profile(owner_id=owner, profile_id=p.id, command=cmd)
        assert replay.configuration_version == 2 and replay.source_key.startswith("ed_rss_")
        with pytest.raises(ApplicationError, match="idempotency_conflict"):
            service.save_profile(
                owner_id=owner, profile_id=p.id, command=cmd.model_copy(update={"name": "Changed"})
            )
        with pytest.raises(ApplicationError, match="resource_not_found"):
            service.get_profile(owner_id=uuid4(), profile_id=p.id)
        assert service.list_runs(owner_id=owner, profile_id=p.id) == ()
        with s.begin():
            before = s.scalar(select(ContentRecord.id))
            due = list_due_editorial_sources_in_transaction(s, now=NOW)
            assert before is None and len(due) == 1 and due[0].revision == 2


def test_source_page_atomically_reuses_original_content_evidence_and_cursor(engine):
    with Session(engine, expire_on_commit=False) as s:
        service, owner, p, _ = setup(s)
        j, op = job(s, owner, p)
        prepared = begin(service, owner, p, j, op)
        assert prepared.should_collect
        service.stage_page(owner_id=owner, run_id=prepared.result.run_id, page=page(material()))
        applied = service.apply_page(owner_id=owner, run_id=prepared.result.run_id)
        assert applied.status == "succeeded" and applied.created == 1
        assert service.apply_page(owner_id=owner, run_id=prepared.result.run_id) == applied
        result = service.get_profile(owner_id=owner, profile_id=p.id)
        assert result.last_ok_at == NOW and result.health == "ok"
        with s.begin():
            record = s.scalar(select(ContentRecord))
            receipt = s.scalar(select(EditorialSourceMaterialReceipt))
            run = s.get(EditorialSourceRun, prepared.result.run_id)
            assert record.source_key == p.source_key and record.id == receipt.content_id
            assert receipt.first_import and receipt.material_metadata["content_format"] == "text"
            assert run.prepared_page is None
            assert s.scalar(text("SELECT count(*) FROM evidence_resources")) == 1
            assert s.scalar(text("SELECT count(*) FROM source_capability_evidence")) == 1


def test_html_and_media_changes_create_fixed_versions_and_revocation_blocks_reads(engine):
    from content.editorial_rendered import read_editorial_rendered_in_transaction
    from content.editorial_rendered_models import ContentRenderedMaterial

    with Session(engine, expire_on_commit=False) as s:
        service, owner, p, _ = setup(s)
        originals = []
        bodies = (
            '<p>Full controlled original source content<img src="/one.png"></p>',
            '<p>Full controlled original source content<img src="/one.png"></p>',
            '<strong>Full controlled original source content<img src="/one.png"></strong>',
            '<strong>Full controlled original source content<img src="/two.png"></strong>',
        )
        for body in bodies:
            j, op = job(s, owner, p)
            prepared = begin(service, owner, p, j, op)
            service.stage_page(
                owner_id=owner,
                run_id=prepared.result.run_id,
                page=page(material(content_format="html", body_html=body)),
            )
            assert (
                service.apply_page(owner_id=owner, run_id=prepared.result.run_id).status
                == "succeeded"
            )
            with s.begin():
                receipt = s.scalar(select(EditorialSourceMaterialReceipt))
                view = read_editorial_rendered_in_transaction(
                    s,
                    owner_id=owner,
                    content_id=receipt.content_id,
                    content_version_id=receipt.content_version_id,
                    now=NOW,
                )
                assert view is not None and view.body_format == "html"
                originals.append(view)
        assert originals[0] == originals[1]
        assert len({view.content_id for view in originals}) == 1
        assert len({view.content_version_id for view in originals}) == 3
        assert originals[2].sha256 != originals[3].sha256
        assert originals[3].media[0].url.endswith("/two.png")
        with s.begin():
            assert len(list(s.scalars(select(ContentRenderedMaterial)))) == 3
            old = read_editorial_rendered_in_transaction(
                s,
                owner_id=owner,
                content_id=originals[0].content_id,
                content_version_id=originals[0].content_version_id,
                now=NOW,
            )
            assert old == originals[0] and "<p>" in old.body
            assert (
                read_editorial_rendered_in_transaction(
                    s,
                    owner_id=uuid4(),
                    content_id=old.content_id,
                    content_version_id=old.content_version_id,
                    now=NOW,
                )
                is None
            )
        with s.begin():
            s.execute(
                text("UPDATE source_access_policies SET enabled=false WHERE owner_id=:owner"),
                {"owner": owner},
            )
        with s.begin():
            assert (
                read_editorial_rendered_in_transaction(
                    s,
                    owner_id=owner,
                    content_id=old.content_id,
                    content_version_id=old.content_version_id,
                    now=NOW,
                )
                is None
            )

        with s.begin():
            s.execute(
                text("UPDATE source_access_policies SET enabled=true WHERE owner_id=:owner"),
                {"owner": owner},
            )
            s.execute(
                text(
                    "UPDATE evidence_retention_policies SET data_class='raw' WHERE owner_id=:owner"
                ),
                {"owner": owner},
            )
        with s.begin():
            assert (
                read_editorial_rendered_in_transaction(
                    s,
                    owner_id=owner,
                    content_id=old.content_id,
                    content_version_id=old.content_version_id,
                    now=NOW,
                )
                is None
            )


def test_sink_failure_keeps_staged_page_and_rolls_back_content_and_cursor(engine):
    with Session(engine, expire_on_commit=False) as s:
        service, owner, p, _ = setup(s)
        j, op = job(s, owner, p)
        prepared = begin(service, owner, p, j, op)
        service.stage_page(owner_id=owner, run_id=prepared.result.run_id, page=page(material()))

        def broken(session, owner, command):
            from content.editorial_ingest import EditorialContentIngestService

            EditorialContentIngestService(session, clock=lambda: NOW).ingest_in_transaction(
                owner_id=owner, command=command
            )
            raise RuntimeError("controlled sink failure")

        with pytest.raises(RuntimeError):
            service.apply_page(owner_id=owner, run_id=prepared.result.run_id, sink=broken)
        s.rollback()
        with s.begin():
            assert s.scalar(select(ContentRecord.id)) is None
            assert s.get(EditorialSourceProfile, p.id).cursor["initialized_at"] is None
            assert s.get(EditorialSourceRun, prepared.result.run_id).status == "staged"
        recovered = begin(service, owner, p, j, op)
        assert not recovered.should_collect and recovered.prepared_page is not None
        assert service.apply_page(owner_id=owner, run_id=recovered.result.run_id).created == 1


def test_abandoned_provider_run_is_unknown_until_audited_manual_ack(engine):
    with Session(engine, expire_on_commit=False) as s:
        service, owner, p, _ = setup(s)
        j, op = job(s, owner, p)
        first = begin(service, owner, p, j, op)
        assert first.should_collect
        replay = begin(service, owner, p, j, op)
        assert replay.result.status == "unknown" and not replay.should_collect
        nextjob, nextop = job(s, owner, p)
        with pytest.raises(ApplicationError, match="editorial_version_conflict"):
            begin(service, owner, p, nextjob, nextop)
        with s.begin():
            assert not list_due_editorial_sources_in_transaction(s, now=NOW + timedelta(days=1))
        review = EditorialRunReviewInput(
            operation_id=uuid4(),
            expected_revision=2,
            reason="Provider receipt checked by operator",
            actor="operator",
            action="acknowledge_unknown",
        )
        resolved = service.review_run(
            owner_id=owner, profile_id=p.id, run_id=first.result.run_id, command=review
        )
        assert resolved.status == "cancelled"
        assert (
            service.review_run(
                owner_id=owner, profile_id=p.id, run_id=first.result.run_id, command=review
            )
            == resolved
        )
        assert service.get_profile(owner_id=owner, profile_id=p.id).revision == 3


def test_partial_page_keeps_coverage_cursor_and_permission_revocation_blocks_commit(engine):
    with Session(engine, expire_on_commit=False) as s:
        service, owner, p, _ = setup(s)
        j, op = job(s, owner, p)
        prepared = begin(service, owner, p, j, op)
        service.stage_page(
            owner_id=owner,
            run_id=prepared.result.run_id,
            page=page(material(), status="partial", reason="gap_pending"),
        )
        assert service.apply_page(owner_id=owner, run_id=prepared.result.run_id).status == "partial"
        with s.begin():
            assert s.get(EditorialSourceProfile, p.id).cursor["initialized_at"] is None
        j2, op2 = job(s, owner, p)
        nextprepared = begin(service, owner, p, j2, op2)
        service.stage_page(
            owner_id=owner, run_id=nextprepared.result.run_id, page=page(material("Revised model"))
        )
        with s.begin():
            s.execute(
                text("UPDATE source_access_policies SET enabled=false WHERE source_key=:key"),
                {"key": p.source_key},
            )
        with pytest.raises(SourceAccessUnavailableError):
            service.apply_page(owner_id=owner, run_id=nextprepared.result.run_id)
        s.rollback()
        with s.begin():
            assert s.scalar(text("SELECT count(*) FROM content_versions")) == 1


def test_external_token_bound_owner_version_hash_and_same_original_content(engine):
    with Session(engine, expire_on_commit=False) as s:
        service, owner, p, _ = setup(s, kind="external", external_token=True)
        with pytest.raises(ApplicationError, match="external_source_authentication_required"):
            service.verify_external_token(owner_id=owner, profile_id=p.id, token="incorrect")
        service.verify_external_token(owner_id=owner, profile_id=p.id, token="controlled-token")
        command = ExternalEditorialInput(
            operation_id=uuid4(),
            expected_revision=2,
            configuration_version=2,
            materials=(material(),),
        )
        accepted = service.accept_external(owner_id=owner, profile_id=p.id, command=command)
        assert (
            service.accept_external(owner_id=owner, profile_id=p.id, command=command).id
            == accepted.id
        )
        with pytest.raises(ApplicationError, match="idempotency_conflict"):
            service.accept_external(
                owner_id=owner,
                profile_id=p.id,
                command=command.model_copy(update={"materials": (material("Different"),)}),
            )
        prepared = begin(service, owner, p, accepted, command.operation_id)
        assert not prepared.should_collect and prepared.prepared_page is not None
        assert service.apply_page(owner_id=owner, run_id=prepared.result.run_id).created == 1


def budgets(session, owner):
    from jobs.schemas import BudgetMetric, BudgetPolicyInput, ComponentPolicyInput, CostClass
    from jobs.services import ResourceBudgetService

    ledger = ResourceBudgetService(session, clock=lambda: NOW)
    ledger.save_component_policy(
        owner_id=owner,
        command=ComponentPolicyInput(
            component_key="collector.editorial",
            component_version="aihot-035f7b7f-v1",
            cost_class=CostClass.LOCAL,
            enabled_for_core=True,
            terms_reference="https://example.com/terms",
            reviewed_at=NOW,
        ),
    )
    for metric, units in (
        (BudgetMetric.NETWORK_REQUEST, 10),
        (BudgetMetric.PROVIDER_CNY_MICROS, 1000000),
    ):
        ledger.save_budget_policy(
            owner_id=owner,
            command=BudgetPolicyInput(
                budget_key=f"controlled.{metric.value}",
                metric=metric,
                scope_kind="global",
                limit_units=units,
                window_seconds=3600,
                window_anchor_at=NOW - timedelta(minutes=1),
                enabled=True,
            ),
        )


def test_runtime_factory_actual_ledger_and_empty_success_clock(engine):
    import httpx
    from sqlalchemy.orm import sessionmaker

    from sources.editorial_execution import EditorialSourceExecutor
    from sources.editorial_factory import ConfiguredEditorialCollectorFactory

    sessions = sessionmaker(engine, expire_on_commit=False)
    with sessions() as session:
        _service, owner, profile, _ = setup(session)
        budgets(session, owner)
        j, op = job(session, owner, profile)
        with session.begin():
            session.execute(
                text(
                    "INSERT INTO event_attention_sources (id,owner_id,source_key,selec"
                    "tor_kind,selector_ref,name,interval_seconds,"
                    "mode,enabled,first_party,scheduled,revision,last_successful_fetch"
                    "_at,created_at,updated_at) "
                    "VALUES (:id,:owner,:key,'source',:key,'Controlled',1800,'editoria"
                    "l',true,false,true,1,NULL,:now,:now)"
                ),
                dict(id=uuid4(), owner=owner, key=profile.source_key, now=NOW),
            )
    requests = []

    def handler(request):
        requests.append(request.url)
        return httpx.Response(
            200, text='<rss version="2.0"><channel><title>Controlled</title></channel></rss>'
        )

    factory = ConfiguredEditorialCollectorFactory(
        sessions,
        owner_id=owner,
        job_id=j.id,
        operation_id=op,
        public_enabled=True,
        transport=httpx.MockTransport(handler),
        clock=lambda: NOW,
    )
    result = EditorialSourceExecutor(
        sessions, collector_factory=factory, clock=lambda: NOW
    ).execute(
        owner_id=owner,
        profile_id=profile.id,
        configuration_version=profile.configuration_version,
        revision=profile.revision,
        job_id=j.id,
        operation_id=op,
    )
    assert result.status == "succeeded" and result.found == 0 and len(requests) == 1
    with sessions.begin() as session:
        assert (
            session.scalar(
                text(
                    "SELECT used_units FROM resource_budget_windows w JOIN resource_bu"
                    "dget_policies p ON p.id=w.budget_policy_id WHERE w.owner_id=:owne"
                    "r AND p.metric='network_request'"
                ),
                dict(owner=owner),
            )
            == 1
        )
        assert (
            session.scalar(
                text(
                    "SELECT last_successful_fetch_at FROM event_attention_sources WHER"
                    "E owner_id=:owner"
                ),
                dict(owner=owner),
            )
            == NOW
        )
        assert (
            session.scalar(
                text("SELECT count(*) FROM resource_usage_attempts WHERE owner_id=:owner"),
                dict(owner=owner),
            )
            == 1
        )


def test_runtime_factory_unknown_settles_and_blocks_automatic_retry(engine):
    import httpx
    from sqlalchemy.orm import sessionmaker

    from sources.editorial_execution import EditorialSourceExecutor
    from sources.editorial_factory import ConfiguredEditorialCollectorFactory

    sessions = sessionmaker(engine, expire_on_commit=False)
    with sessions() as session:
        _service, owner, profile, _ = setup(session)
        budgets(session, owner)
        j, op = job(session, owner, profile)
    requests = []

    def handler(request):
        requests.append(request.url)
        raise httpx.ReadTimeout("controlled unknown")

    factory = ConfiguredEditorialCollectorFactory(
        sessions,
        owner_id=owner,
        job_id=j.id,
        operation_id=op,
        public_enabled=True,
        transport=httpx.MockTransport(handler),
        clock=lambda: NOW,
    )
    executor = EditorialSourceExecutor(sessions, collector_factory=factory, clock=lambda: NOW)
    arguments = dict(
        owner_id=owner,
        profile_id=profile.id,
        configuration_version=profile.configuration_version,
        revision=profile.revision,
        job_id=j.id,
        operation_id=op,
    )
    assert executor.execute(**arguments).status == "unknown"
    assert executor.execute(**arguments).status == "unknown" and len(requests) == 1
    with sessions.begin() as session:
        assert (
            session.scalar(
                text(
                    "SELECT used_units FROM resource_budget_windows w JOIN resource_bu"
                    "dget_policies p ON p.id=w.budget_policy_id WHERE w.owner_id=:owne"
                    "r AND p.metric='network_request'"
                ),
                dict(owner=owner),
            )
            == 1
        )
        assert (
            session.scalar(
                text("SELECT last_ok_at FROM editorial_source_profiles WHERE owner_id=:owner"),
                dict(owner=owner),
            )
            is None
        )
        assert (
            list_due_editorial_sources_in_transaction(session, now=NOW + timedelta(hours=1)) == ()
        )


def test_runtime_money_uses_original_ledger_and_releases_no_request(engine):
    from decimal import Decimal

    from sqlalchemy.orm import sessionmaker

    from sources.editorial_factory import EditorialRequestMeter

    sessions = sessionmaker(engine, expire_on_commit=False)
    with sessions() as session:
        service, owner, profile, _ = setup(session)
        budgets(session, owner)
        j, op = job(session, owner, profile)
        prepared = begin(service, owner, profile, j, op)
    meter = EditorialRequestMeter(
        sessions,
        owner_id=owner,
        job_id=j.id,
        run_id=prepared.result.run_id,
        operation_id=op,
        source_ref="jina",
        connection_id=profile.connection_id,
        paid_caps_cny_micros={"jina_listing": 140000},
        clock=lambda: NOW,
    )
    assert meter.before_paid("jina_listing")
    meter.report_cost("jina_listing", Decimal(0))
    assert meter.before(1)
    meter.settle(1, "succeeded")
    assert meter.before_paid("jina_listing")
    meter.report_cost("jina_listing", Decimal("0.0000011"))
    with sessions.begin() as session:
        assert (
            session.scalar(
                text(
                    "SELECT used_units FROM resource_budget_windows w JOIN resource_bu"
                    "dget_policies p ON p.id=w.budget_policy_id WHERE w.owner_id=:owne"
                    "r AND p.metric='provider_cny_micros'"
                ),
                dict(owner=owner),
            )
            == 2
        )
        assert (
            session.scalar(
                text(
                    "SELECT reserved_units FROM resource_budget_windows w JOIN resourc"
                    "e_budget_policies p ON p.id=w.budget_policy_id WHERE w.owner_id=:"
                    "owner AND p.metric='provider_cny_micros'"
                ),
                dict(owner=owner),
            )
            == 0
        )


def test_profile_audit_is_atomic_and_external_transaction_rollback(engine):
    with Session(engine) as session:
        service, owner, profile, command = setup(session)
        with session.begin():
            audit = session.execute(
                text(
                    "SELECT status,reason,after_state FROM operations_audit_operations"
                    " WHERE owner_id=:owner AND operation_id=:op"
                ),
                dict(owner=owner, op=command.operation_id),
            ).one()
            assert audit.status == "succeeded" and audit.reason == command.reason
            assert audit.after_state["revision"] == profile.revision
        op = uuid4()
        with pytest.raises(RuntimeError), session.begin():
            service.save_profile_in_transaction(
                owner_id=owner,
                profile_id=profile.id,
                command=command.model_copy(
                    update={
                        "operation_id": op,
                        "expected_revision": profile.revision,
                        "name": "Rolled back",
                    }
                ),
            )
            raise RuntimeError("simulate outer operator rollback")
        assert service.get_profile(owner_id=owner, profile_id=profile.id).name == profile.name
        with session.begin():
            assert (
                session.scalar(
                    text(
                        "SELECT count(*) FROM operations_audit_operations WHERE owner_id=:"
                        "owner AND operation_id=:op"
                    ),
                    dict(owner=owner, op=op),
                )
                == 0
            )


def test_source_schedule_and_worker_use_actual_job_lease_and_outbox(engine):
    import httpx
    from sqlalchemy.orm import sessionmaker

    from core.config import Settings
    from jobs.execution import JobExecutionService
    from jobs.schemas import JobAcceptedMessage, JobStatus
    from sources.editorial_job import EditorialSourceJobExecutor
    from sources.editorial_schedule import enqueue_due_editorial_sources_in_transaction

    sessions = sessionmaker(engine, expire_on_commit=False)
    with sessions() as session:
        _, owner, _profile, _ = setup(session)
        budgets(session, owner)
        with session.begin():
            assert enqueue_due_editorial_sources_in_transaction(session, NOW, enabled=True) == 1
            assert enqueue_due_editorial_sources_in_transaction(session, NOW, enabled=True) == 0
        with session.begin():
            assert (
                session.scalar(
                    text("SELECT count(*) FROM jobs WHERE owner_id=:owner"), dict(owner=owner)
                )
                == 1
            )
            outbox = session.execute(
                text(
                    "SELECT id,event_type,payload FROM outbox_messages WHERE aggregate"
                    "_id IN (SELECT id FROM jobs WHERE owner_id=:owner)"
                ),
                dict(owner=owner),
            ).one()
        message = JobAcceptedMessage.model_validate(
            dict(
                **outbox.payload,
                message_id=outbox.id,
                event_type=outbox.event_type,
                schema_version=2,
            )
        )
        lease = JobExecutionService(session, lease_seconds=30, clock=lambda: NOW).acquire(
            job_id=message.job_id, worker_id="controlled-source"
        )
    calls = []

    def handler(request):
        calls.append(request.url)
        return httpx.Response(
            200, text='<rss version="2.0"><channel><title>Controlled</title></channel></rss>'
        )

    executor = EditorialSourceJobExecutor(
        sessions,
        Settings(
            _env_file=None,
            database_url=os.environ["HOTKEY_TEST_DATABASE_URL"],
            editorial_sources_enabled=True,
            editorial_public_requests_enabled=True,
        ),
        transport=httpx.MockTransport(handler),
        clock=lambda: NOW,
    )
    assert executor.execute(message, lease).status is JobStatus.SUCCEEDED
    assert executor.execute(message, lease).status is JobStatus.SUCCEEDED and len(calls) == 1
    with sessions.begin() as session:
        assert (
            session.scalar(
                text("SELECT requests_sent FROM jobs WHERE id=:id"), dict(id=message.job_id)
            )
            == 1
        )
        assert enqueue_due_editorial_sources_in_transaction(session, NOW, enabled=True) == 0


def test_collection_profile_synchronizes_editorial_source_without_publication_grants(engine):
    from analysis.editorial_services import EditorialService

    with Session(engine) as session:
        service, owner, profile, command = setup(session)
        with session.begin():
            linked = EditorialService(session).get_source_in_transaction(
                owner_id=owner, source_key=profile.source_key
            )
            assert linked is not None and linked.enabled and linked.tier == profile.tier
            assert linked.name == profile.name and linked.source_kind == "rss"
        profile = service.save_profile(
            owner_id=owner,
            profile_id=profile.id,
            command=command.model_copy(
                update={
                    "operation_id": uuid4(),
                    "expected_revision": profile.revision,
                    "participation_mode": "isolated",
                    "tier": "T3",
                }
            ),
        )
        with session.begin():
            linked = EditorialService(session).get_source_in_transaction(
                owner_id=owner, source_key=profile.source_key
            )
            assert linked is not None and not linked.enabled and linked.tier == "UNGRADED"
            assert (
                session.scalar(
                    text("SELECT count(*) FROM publication_source_policies WHERE owner_id=:owner"),
                    dict(owner=owner),
                )
                == 0
            )


def test_operator_can_revise_returned_self_connection_binding_but_not_stale_version(engine):
    with Session(engine, expire_on_commit=False) as session:
        service, owner, profile, command = setup(session)
        assert profile.connection_id is not None
        saved = service.save_profile(
            owner_id=owner,
            profile_id=profile.id,
            command=command.model_copy(
                update=dict(
                    operation_id=uuid4(),
                    expected_revision=profile.revision,
                    name="Revised owned gate",
                    connection_id=profile.connection_id,
                    connection_version=profile.connection_version,
                )
            ),
        )
        assert saved.name == "Revised owned gate"
        assert saved.connection_id == profile.connection_id
        assert saved.connection_version == profile.connection_version + 1
        with pytest.raises(ApplicationError) as stale:
            service.save_profile(
                owner_id=owner,
                profile_id=profile.id,
                command=command.model_copy(
                    update=dict(
                        operation_id=uuid4(),
                        expected_revision=saved.revision,
                        connection_id=profile.connection_id,
                        connection_version=profile.connection_version,
                    )
                ),
            )
        assert stale.value.code == "connection_version_conflict"
        assert service.get_profile(owner_id=owner, profile_id=profile.id) == saved


def test_personal_source_ingests_with_existing_content_contract_and_icon_identity(engine):
    from connections.editorial_icon_services import enqueue_due_source_icons_in_transaction
    from connections.editorial_topic_sources import list_editorial_topic_sources_in_transaction
    from publication.schemas import SourcePolicyInput
    from publication.services import PublicationService
    from sources.icons_schemas import SourceIconSeed

    with Session(engine, expire_on_commit=False) as s:
        service, owner, p, _ = setup(s, personal=True)
        assert p.source_key.startswith("ed_personal_rss_")
        assert service.list_profiles(owner_id=owner) == ()
        assert service.list_profiles(owner_id=owner, personal=True)[0].id == p.id
        j, op = job(s, owner, p)
        prepared = begin(service, owner, p, j, op)
        service.stage_page(owner_id=owner, run_id=prepared.result.run_id, page=page(material()))
        applied = service.apply_page(owner_id=owner, run_id=prepared.result.run_id)
        assert applied.status == "succeeded" and applied.created == 1
        SourceIconSeed(
            owner_id=owner,
            profile_id=p.id,
            source_key=p.source_key,
            configuration_version=p.configuration_version,
            profile_revision=p.revision,
            policy_version=p.policy_version,
            connection_id=p.connection_id,
            connection_version=p.connection_version,
            configuration=p.configuration,
            scheduled_for_at=NOW,
        )
        with s.begin():
            choices = list_editorial_topic_sources_in_transaction(s, owner_id=owner, now=NOW)
            assert len(choices) == 1 and choices[0].selectable
            enqueue_due_source_icons_in_transaction(s, now=NOW, enabled=True)
        with pytest.raises(ApplicationError, match="invalid_publication_input"), s.begin():
            PublicationService(s).save_source_policy_in_transaction(
                owner_id=owner,
                actor_id=owner,
                source_key=p.source_key,
                command=SourcePolicyInput(
                    operation_id=uuid4(),
                    expected_revision=0,
                    participation_mode="editorial",
                    license_name="Controlled test",
                    reason="Personal sources cannot be made public",
                ),
            )


def test_personal_http_configuration_is_session_owned_csrf_protected_and_idempotent(engine):
    from fastapi.testclient import TestClient
    from tests.conftest import authenticate_test_client

    from connections.editorial_schemas import PersonalSourceInput
    from core.config import Settings
    from main import create_app

    app = create_app(
        Settings(
            _env_file=None,
            environment="test",
            log_level="WARNING",
            database_url=engine.url.render_as_string(hide_password=False),
        )
    )
    command = PersonalSourceInput(
        operation_id=uuid4(),
        name="My feed",
        configuration={
            "kind": "rss",
            "feed_url": "https://example.com/feed",
            "allowed_hosts": ["example.com"],
        },
    )
    body = command.model_dump(mode="json")
    path = "/api/sources/personal"
    with TestClient(app) as client:
        assert client.get(path).status_code == 401
        assert client.post(path, json=body).status_code == 401
        owner = authenticate_test_client(client)
        assert client.post(path, json=body).status_code == 403
        headers = {"X-HotKey-CSRF": client.cookies["hotkey_csrf"]}
        assert client.get(path).json() == []
        created = client.post(path, json=body, headers=headers)
        assert created.status_code == 201, created.text
        profile = created.json()
        assert not profile["enabled"] and profile["source_key"].startswith("ed_personal_rss_")
        assert client.post(path, json=body, headers=headers).json()["id"] == profile["id"]
        assert (
            client.post(path, json={**body, "name": "Changed"}, headers=headers).status_code == 409
        )
        update = {**body, "operation_id": str(uuid4()), "expected_revision": 1, "name": "New name"}
        assert (
            client.put(f"{path}/{profile['id']}", json=update, headers=headers).status_code == 200
        )
        stale = {**update, "operation_id": str(uuid4())}
        assert client.put(f"{path}/{profile['id']}", json=stale, headers=headers).status_code == 409
        enable = {**update, "operation_id": str(uuid4()), "expected_revision": 2, "enabled": True}
        assert (
            client.put(f"{path}/{profile['id']}", json=enable, headers=headers).status_code == 409
        )
        with app.state.session_factory() as s:
            assert s.scalar(text("SELECT count(*) FROM jobs")) == 0
            assert s.scalar(text("SELECT count(*) FROM content_records")) == 0
            site_cmd = command.model_copy(update={"operation_id": uuid4()}).editorial_input()
            site = EditorialSourceService(s).save_profile(owner_id=owner, command=site_cmd)
        assert len(client.get(path).json()) == 1
        assert (
            client.put(
                f"{path}/{site.id}", json={**update, "operation_id": str(uuid4())}, headers=headers
            ).status_code
            == 404
        )
        replay_site = site_cmd.model_dump(
            mode="json",
            exclude={
                "reason",
                "participation_mode",
                "tier",
                "first_party",
                "connection_id",
                "connection_version",
            },
        )
        assert client.post(path, json=replay_site, headers=headers).status_code == 404
        authenticate_test_client(client)
        headers = {"X-HotKey-CSRF": client.cookies["hotkey_csrf"]}
        assert client.get(path).json() == []
        assert (
            client.put(f"{path}/{profile['id']}", json=update, headers=headers).status_code == 404
        )
        paid = {**body, "operation_id": str(uuid4()), "configuration": {"kind": "external"}}
        assert client.post(path, json=paid, headers=headers).status_code == 422
