from datetime import timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker
from tests.integration.test_editorial_source_profiles import NOW, begin, job, material, page, setup
from tests.integration.test_editorial_source_profiles import engine as engine
from tests.integration.test_editorial_topic_matches import _topic

from connections.editorial_body_admission import require_editorial_body_execution_in_transaction
from connections.editorial_body_schemas import EditorialBodyApprovalInput
from connections.editorial_models import EditorialSourceMaterialReceipt, EditorialSourceRun
from connections.editorial_services import EditorialSourceService
from content.models import (
    ContentObservation,
    ContentObservationInput,
    ContentRecord,
    ContentTopicMatch,
    ContentVersion,
)
from content.services import ContentService
from content.version_inputs import (
    observations_readable_in_transaction,
    version_inputs_readable_in_transaction,
)
from core.errors import ApplicationError
from sources.contracts import SourceDocument, WebPageResult
from sources.editorial_body import LocalEditorialBodyFetcher
from sources.editorial_body_review import EditorialBodyReview
from sources.editorial_execution import EditorialSourceExecutor
from sources.editorial_schemas import EditorialBodyConfiguration, EditorialMaterial, fingerprint


def configure(session, *, approve=True, max_fetches=5):
    service, owner, profile, command = setup(session)
    review = EditorialBodyReview(
        read_reference="controlled-read",
        save_reference="controlled-save",
        fee_reference="controlled-zero",
        egress_reference="controlled-egress",
        request_bound_reference="controlled-request-bound",
        deployment_reference="controlled-local-runtime",
        reviewed_at=NOW - timedelta(hours=1),
        expires_at=NOW + timedelta(hours=1),
    )
    config = profile.configuration.model_copy(
        update={
            "body_extraction": EditorialBodyConfiguration(
                enabled=True, allowed_hosts=("example.com",), review=review, max_fetches=max_fetches
            )
        }
    )
    profile = service.save_profile(
        owner_id=owner,
        profile_id=profile.id,
        command=command.model_copy(
            update={
                "operation_id": uuid4(),
                "expected_revision": profile.revision,
                "configuration": config,
            }
        ),
    )
    with session.begin():
        session.execute(
            text(
                "UPDATE source_access_policies SET field_purposes=field_purposes "
                "|| CAST(:fields AS jsonb) WHERE owner_id=:owner AND source_key=:key"
            ),
            {
                "fields": (
                    '{"text_origin_ref":"controlled origin","truncation_reason":"controlled limit"}'
                ),
                "owner": owner,
                "key": profile.source_key,
            },
        )
    if approve:
        service.approve_body(owner_id=owner, profile_id=profile.id, command=approval(profile))
    return service, owner, profile


def approval(profile):
    return EditorialBodyApprovalInput(
        operation_id=uuid4(),
        expected_revision=profile.revision,
        configuration_version=profile.configuration_version,
        configuration_sha256=fingerprint(profile.configuration.model_dump(mode="json")).hex(),
        reason="Controlled exact deployment and read/save/zero-fee review",
        review=profile.configuration.body_extraction.review,
    )


def summary(identity="url:https://example.com/post"):
    return EditorialMaterial(
        url="https://example.com/post",
        identity_key=identity,
        title="Original model title",
        excerpt="Source teaser",
        published_at=NOW - timedelta(hours=1),
    )


def feed(session, service, owner, profile, *materials):
    accepted, operation = job(session, owner, profile)
    prepared = begin(service, owner, profile, accepted, operation)
    service.stage_page(
        owner_id=owner, run_id=prepared.result.run_id, page=page(*(materials or (summary(),)))
    )
    result = service.apply_page(owner_id=owner, run_id=prepared.result.run_id)
    return accepted, operation, prepared.result.run_id, result


def response(target):
    return WebPageResult(
        document=SourceDocument(
            request_url=target.target_url,
            final_url=target.target_url,
            title="Untrusted provider title",
            text="# needle original complete body",
            text_scope="full",
            observed_at=NOW,
            published_at=NOW,
            content_fingerprint="a" * 64,
            extractor_version="firecrawl/2.11.162",
        ),
        target_status_code=200,
        collector_call_count=1,
        target_request_count=None,
    )


def test_body_feed_checkpoint_same_identity_new_observation_all_inputs_and_rematch(engine):
    with Session(engine, expire_on_commit=False) as session:
        service, owner, profile = configure(session)
        topic = _topic(session, owner, profile.id, keyword="needle")
        accepted, _, run_id, result = feed(session, service, owner, profile)
        assert result.status == "running" and result.created == 1
        with session.begin():
            assert session.scalar(select(ContentTopicMatch)) is None
            run = session.get(EditorialSourceRun, run_id)
            assert run.status == "staged" and run.prepared_page["_body_phase"]["next_index"] == 0
        target = service.begin_body_request(owner_id=owner, run_id=run_id)
        service.apply_body_response(owner_id=owner, run_id=run_id, response=response(target))
        # New service/process resumes the committed result reference without feed or HTTP replay.
        service = EditorialSourceService(session, clock=lambda: NOW)
        assert service.apply_page(owner_id=owner, run_id=run_id).created == 1
        completed = service.finish_body_phase(owner_id=owner, run_id=run_id)
        assert completed.status == "succeeded" and completed.created == 1 and completed.revised == 1
        assert service.apply_page(owner_id=owner, run_id=run_id) == completed
        with session.begin():
            records = session.scalars(select(ContentRecord)).all()
            observations = session.scalars(select(ContentObservation)).all()
            assert len(records) == 1 and len(observations) == 2
            assert (
                records[0].id == target.content_id
                and records[0].native_scope == f"editorial-profile:{profile.id}"
            )
            assert {o.job_id for o in observations} == {accepted.id}
            assert len({o.source_operation_id for o in observations}) == 2
            body = next(o for o in observations if o.id != target.feed_observation_id)
            version = session.get(ContentVersion, body.content_version_id)
            assert version.text_scope == "full" and version.text_origin == "machine_extracted"
            assert (
                version.text_origin_ref == "firecrawl/2.11.162"
                and version.title == "Original model title"
            )
            assert set(
                session.scalars(
                    select(ContentObservationInput.input_observation_id).where(
                        ContentObservationInput.output_observation_id == body.id
                    )
                )
            ) == {target.feed_observation_id}
            match = session.scalar(
                select(ContentTopicMatch).where(ContentTopicMatch.topic_id == topic.id)
            )
            assert match.content_version_id == version.id and set(match.input_observation_ids) == {
                str(target.feed_observation_id),
                str(body.id),
            }
            assert version_inputs_readable_in_transaction(
                session, owner_id=owner, content_version_ids=(version.id,), now=NOW
            )
        # Same feed in a new original Job cannot downgrade body v2 or send another body request.
        _, _, _, replay = feed(session, service, owner, profile)
        assert replay.status == "succeeded" and replay.created == replay.revised == 0
        with session.begin():
            assert session.scalar(select(ContentObservationInput.output_observation_id)) == body.id
            assert len(session.scalars(select(ContentObservation)).all()) == 2
            session.execute(
                text(
                    "UPDATE evidence_resources SET expires_at=:now "
                    "WHERE owner_id=:owner AND resource_id=:observation"
                ),
                {"owner": owner, "observation": target.feed_observation_id, "now": NOW},
            )
        with session.begin():
            assert not observations_readable_in_transaction(
                session,
                owner_id=owner,
                observation_ids=(body.id,),
                now=NOW + timedelta(seconds=1),
            )
        with pytest.raises(ApplicationError, match="resource_not_found"):
            ContentService(session, clock=lambda: NOW + timedelta(seconds=1)).get_content(
                owner_id=owner, content_id=target.content_id
            )


def test_unapproved_body_is_zero_http_partial_and_does_not_advance_feed_coverage(engine):
    sessions = sessionmaker(engine, expire_on_commit=False)
    calls = []

    class Collector:
        def collect(self, *_):
            return page(summary())

        def close(self):
            pass

    with sessions() as session:
        _service, owner, profile = configure(session, approve=False)
        accepted, operation = job(session, owner, profile)

    def body_factory(prepared):
        def admit(target):
            with sessions.begin() as session:
                try:
                    return require_editorial_body_execution_in_transaction(
                        session,
                        owner_id=owner,
                        profile_id=profile.id,
                        configuration_version=profile.configuration_version,
                        revision=profile.revision,
                        now=NOW,
                    )
                except ApplicationError:
                    return None

        return LocalEditorialBodyFetcher(
            base_url="http://127.0.0.1:3002",
            configuration_sha256=fingerprint(
                prepared.profile.configuration.model_dump(mode="json")
            ).hex(),
            admission=admit,
            before_request=lambda _: True,
            settle=lambda *_: None,
            transport=httpx.MockTransport(lambda request: calls.append(request)),
            clock=lambda: NOW,
        )

    executor = EditorialSourceExecutor(
        sessions,
        collector_factory=lambda _: Collector(),
        body_fetcher_factory=body_factory,
        clock=lambda: NOW,
    )
    result = executor.execute(
        owner_id=owner,
        profile_id=profile.id,
        configuration_version=profile.configuration_version,
        revision=profile.revision,
        job_id=accepted.id,
        operation_id=operation,
    )
    assert result.status == "partial" and result.reason == "body_access_denied" and calls == []
    with sessions() as session:
        run = session.get(EditorialSourceRun, result.run_id)
        receipt = session.scalar(select(EditorialSourceMaterialReceipt))
        assert run.status == "partial" and receipt.body_status == "pending"
        assert (
            EditorialSourceService(session, clock=lambda: NOW)
            .get_profile(owner_id=owner, profile_id=profile.id)
            .last_ok_at
            is None
        )
        content_id, version_id, observation_id = (
            receipt.content_id,
            receipt.content_version_id,
            receipt.observation_id,
        )
    # A fresh poll of the unchanged excerpt is a feed duplicate. It must not
    # borrow the old Job's observation to start another body request.
    with sessions() as session:
        repeated, repeated_operation = job(session, owner, profile)
    duplicate = executor.execute(
        owner_id=owner,
        profile_id=profile.id,
        configuration_version=profile.configuration_version,
        revision=profile.revision,
        job_id=repeated.id,
        operation_id=repeated_operation,
    )
    assert duplicate.status == "succeeded"
    assert duplicate.found == 1 and duplicate.created == duplicate.revised == 0 and calls == []
    with sessions() as session, session.begin():
        assert session.get(EditorialSourceRun, duplicate.run_id).prepared_page is None
        assert session.get(EditorialSourceRun, result.run_id).status == "partial"
        assert len(session.scalars(select(ContentObservation)).all()) == 1
        assert len(session.scalars(select(ContentVersion)).all()) == 1
        assert session.get(ContentObservation, observation_id).job_id == accepted.id
        assert session.scalar(text("SELECT count(*) FROM jobs")) == 2
    with sessions() as session:
        read = ContentService(session, clock=lambda: NOW).get_content(
            owner_id=owner, content_id=content_id
        )
        assert read.latest_observation.content_version.id == version_id
        assert read.latest_observation.content_version.body == "Source teaser"


def test_abandoned_body_boundary_is_unknown_without_another_request_or_feed_apply(engine):
    with Session(engine) as session:
        service, owner, profile = configure(session)
        accepted, operation, run_id, result = feed(session, service, owner, profile)
        target = service.begin_body_request(owner_id=owner, run_id=run_id)
        replay = begin(service, owner, profile, accepted, operation)
        assert not replay.should_collect and replay.result.status == "running"
        assert service.apply_page(owner_id=owner, run_id=run_id) == result
        unknown = service.finish_body_phase(owner_id=owner, run_id=run_id)
        assert unknown.status == "unknown" and unknown.reason == "abandoned_body_request"
        with session.begin():
            assert len(session.scalars(select(ContentObservation)).all()) == 1
            assert session.get(EditorialSourceRun, run_id).prepared_page["_body_phase"]["targets"][
                0
            ]["feed_observation_id"] == str(target.feed_observation_id)


@pytest.mark.parametrize("mutation", ["guard", "terminal", "configuration", "permission"])
def test_body_commit_rechecks_original_lease_job_configuration_and_source_permission(
    engine, mutation
):
    with Session(engine) as session:
        service, owner, profile = configure(session)
        accepted, _, run_id, _ = feed(session, service, owner, profile)
        target = service.begin_body_request(owner_id=owner, run_id=run_id)
        returned = response(target)
        with session.begin():
            if mutation == "terminal":
                session.execute(
                    text("UPDATE jobs SET status='succeeded',completed_at=:now WHERE id=:id"),
                    {"id": accepted.id, "now": NOW},
                )
            elif mutation == "configuration":
                session.execute(
                    text("UPDATE editorial_source_profiles SET revision=revision+1 WHERE id=:id"),
                    {"id": profile.id},
                )
            elif mutation == "permission":
                session.execute(
                    text(
                        "UPDATE source_access_policies SET enabled=false "
                        "WHERE owner_id=:owner AND source_key=:key"
                    ),
                    {"owner": owner, "key": profile.source_key},
                )
        with pytest.raises((ApplicationError, RuntimeError)):
            service.apply_body_response(
                owner_id=owner,
                run_id=run_id,
                response=returned,
                guard=(lambda *_: False) if mutation == "guard" else None,
            )
        session.rollback()
        with session.begin():
            assert len(session.scalars(select(ContentObservation)).all()) == 1
            assert session.scalar(select(ContentVersion)).text_scope == "summary"
            phase = session.get(EditorialSourceRun, run_id).prepared_page["_body_phase"]
            assert phase["request_pending"] is True and "response" not in phase


def test_declared_body_limit_is_partial_without_silently_reducing_the_scope(engine):
    with Session(engine) as session:
        service, owner, profile = configure(session, max_fetches=1)
        _, _, run_id, _ = feed(session, service, owner, profile, summary("one"), summary("two"))
        checkpoint = service.body_checkpoint(owner_id=owner, run_id=run_id)
        assert len(checkpoint.targets) == 1 and checkpoint.failure_codes == ("body_target_limit",)
        target = service.begin_body_request(owner_id=owner, run_id=run_id)
        service.apply_body_response(owner_id=owner, run_id=run_id, response=response(target))
        assert service.finish_body_phase(owner_id=owner, run_id=run_id).status == "partial"


def test_confirmed_full_feed_never_creates_a_body_stage(engine):
    with Session(engine) as session:
        service, owner, profile = configure(session, approve=False)
        _, _, run_id, result = feed(session, service, owner, profile, material())
        assert result.status == "succeeded"
        assert service.body_checkpoint(owner_id=owner, run_id=run_id) is None


def test_original_source_job_executes_server_admitted_body_with_lease_and_actual_ledger(engine):
    import os

    from tests.integration.test_editorial_source_profiles import budgets

    from core.config import Settings
    from jobs.execution import JobExecutionService
    from jobs.schemas import BudgetMetric, BudgetPolicyInput, JobAcceptedMessage, JobStatus
    from jobs.services import ResourceBudgetService
    from sources.editorial_job import EditorialSourceJobExecutor

    sessions = sessionmaker(engine, expire_on_commit=False)
    with sessions() as session:
        _, owner, profile = configure(session)
        budgets(session, owner)
        ResourceBudgetService(session, clock=lambda: NOW).save_budget_policy(
            owner_id=owner,
            command=BudgetPolicyInput(
                budget_key="controlled.body.calls",
                metric=BudgetMetric.COLLECTOR_CALL,
                scope_kind="global",
                limit_units=10,
                window_seconds=3600,
                window_anchor_at=NOW - timedelta(minutes=1),
                enabled=True,
            ),
        )
        accepted, _ = job(session, owner, profile)
        with session.begin():
            outbox = session.execute(
                text("SELECT id,event_type,payload FROM outbox_messages WHERE aggregate_id=:id"),
                {"id": accepted.id},
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
            job_id=accepted.id, worker_id="controlled-body"
        )
    calls = []

    def handler(request):
        calls.append((request.method, str(request.url)))
        if request.method == "GET" and str(request.url) == "https://example.com/feed":
            return httpx.Response(
                200,
                text=(
                    '<rss version="2.0"><channel><title>Controlled</title><item>'
                    "<guid>original-guid</guid><title>Original title</title>"
                    "<link>https://example.com/post</link><description>Source teaser</description>"
                    "</item></channel></rss>"
                ),
            )
        assert request.method == "POST" and str(request.url) == "http://127.0.0.1:3002/v2/scrape"
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": {
                    "markdown": "Original complete controlled body",
                    "metadata": {"statusCode": 200, "url": "https://example.com/post"},
                },
            },
        )

    executor = EditorialSourceJobExecutor(
        sessions,
        Settings(
            _env_file=None,
            database_url=os.environ["HOTKEY_TEST_DATABASE_URL"],
            editorial_sources_enabled=True,
            editorial_public_requests_enabled=True,
            firecrawl_enabled=True,
            firecrawl_base_url="http://127.0.0.1:3002",
        ),
        transport=httpx.MockTransport(handler),
        clock=lambda: NOW,
    )
    completed = executor.execute(message, lease)
    assert completed.status is JobStatus.SUCCEEDED
    assert executor.execute(message, lease).status is JobStatus.SUCCEEDED and len(calls) == 2
    with sessions.begin() as session:
        assert (
            session.scalar(text("SELECT requests_sent FROM jobs WHERE id=:id"), {"id": accepted.id})
            == 2
        )
        assert (
            session.scalar(select(ContentRecord)).native_scope == f"editorial-profile:{profile.id}"
        )
        assert {o.job_id for o in session.scalars(select(ContentObservation))} == {accepted.id}
        assert len(session.scalars(select(ContentObservation)).all()) == 2
        usages = session.execute(
            text(
                "SELECT p.metric,w.used_units FROM resource_budget_windows w "
                "JOIN resource_budget_policies p ON p.id=w.budget_policy_id "
                "WHERE w.owner_id=:owner"
            ),
            {"owner": owner},
        ).all()
        usage = dict(usages)
        assert usage["collector_call"] == 1
        assert (
            usage["network_request"]
            == 1 + profile.configuration.body_extraction.max_target_requests
        )
        assert usage.get("provider_cny_micros", 0) == 0
        run = session.scalar(select(EditorialSourceRun))
        assert run.prepared_page["_body_receipt"]["local_collector_calls"] == 1
        assert run.prepared_page["_body_receipt"]["target_request_count"] is None
        assert (
            session.scalar(
                text(
                    "SELECT count(*) FROM resource_usage_attempts u "
                    "JOIN resource_component_policies p ON p.id=u.component_policy_id "
                    "WHERE u.owner_id=:owner AND p.cost_class NOT IN ('local','zero_price')"
                ),
                {"owner": owner},
            )
            == 0
        )
