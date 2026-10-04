"""Real isolated PostgreSQL with controlled source Jobs and model results, no provider calls."""

import json
import os
from datetime import timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker
from tests.integration.test_analysis_pipeline import (
    _make_unreadable,
    _seed_ai_call,
)
from tests.integration.test_analysis_pipeline import (
    analysis_case as analysis_case,
)
from tests.integration.test_content_native_identity import collect, configured
from tests.integration.test_editorial_source_profiles import engine as engine
from tests.unit.test_editorial_native_identity import NOW

from ai.analysis_reading import load_legacy_analysis_call_job_in_transaction
from analysis.alert_reading import (
    load_negative_alert_facts_in_transaction,
    negative_alert_inputs_readable_in_transaction,
)
from analysis.models import ContentAnnotation
from analysis.prompts import ANALYSIS_PROMPT_VERSION
from analysis.reads import (
    analysis_scope_inputs_readable_in_transaction,
    annotation_inputs_readable_in_transaction,
    load_content_annotations_in_transaction,
    load_report_annotation_observation_ids_in_transaction,
    readable_annotation_ids_in_transaction,
    relevant_event_annotation_ids_in_transaction,
    report_annotations_readable_in_transaction,
)
from analysis.schemas import (
    AnalysisJobScope,
    AnalysisPromptItem,
    AnnotationResultState,
    AnnotationStatus,
    AnnotationWrite,
    Sentiment,
)
from analysis.services import (
    AnalysisAnnotateExecutor,
    AnalysisService,
    analysis_operation_id,
    list_relevant_event_annotation_refs_in_transaction,
)
from connections.editorial_services import EditorialSourceService
from content.analysis_inputs import (
    AnalysisObservationManifest,
    analysis_observation_manifests_readable_in_transaction,
    freeze_analysis_observation_inputs_in_transaction,
    require_analysis_observation_inputs_in_transaction,
)
from content.lifecycle import purge_observation_dependants_in_transaction
from content.models import ContentObservation, ContentVersion
from content.report_reading import report_inputs_readable_in_transaction
from content.services import load_post_versions_for_analysis
from core.config import Settings
from core.errors import ApplicationError
from jobs.execution import JobExecutionFailure
from jobs.schemas import JobAcceptanceInput, JobAcceptedMessage, JobObservationContext
from jobs.services import JobService
from monitors.schemas import MonitorTopicCreateInput
from monitors.services import MonitorTopicService
from reports.services import ReportService


def aliases(session):
    first, owner, profile_a = configured(session)
    second, _, profile_b = configured(
        session,
        owner_id=owner,
        route="/threads/search/sample/serpType=recent",
        mode="platform_keyword",
    )
    _, a = collect(session, first, owner, profile_a)
    _, b = collect(session, second, owner, profile_b)
    assert a[:2] == b[:2] and a[2] != b[2]
    return owner, profile_a, profile_b, a, b


def topic(session, owner):
    identifier = uuid4()
    session.execute(
        text(
            "INSERT INTO monitor_topics "
            "(id,owner_id,name,status,readiness_status,current_version,created_at,updated_at) "
            "VALUES (:id,:owner,'Controlled analysis observations','paused',"
            "'pending_source_selection',1,:now,:now)"
        ),
        {"id": identifier, "owner": owner, "now": NOW},
    )
    session.execute(
        text(
            "INSERT INTO monitor_topic_versions "
            "(topic_id,version,created_by,match_any,match_all,exclude,created_at) "
            "VALUES (:topic,1,:owner,'[\"controlled\"]'::jsonb,'[]'::jsonb,'[]'::jsonb,:now)"
        ),
        {"topic": identifier, "owner": owner, "now": NOW},
    )
    return identifier


def freeze(session, owner, *inputs):
    return freeze_analysis_observation_inputs_in_transaction(
        session,
        owner_id=owner,
        post_observations={item[1]: item[2] for item in inputs},
        comment_observations={},
        now=NOW,
    )


def persist(session, owner, topic_id, manifest, *, label, at=NOW, sentiment=Sentiment.NEUTRAL):
    posts = load_post_versions_for_analysis(
        session,
        owner_id=owner,
        content_version_ids=set(manifest.post_observations),
        readable_at=at,
        selected_observations=manifest.post_observations,
    )
    assert {post.content_version_id for post in posts} == set(manifest.post_observations)
    call = uuid4()
    # This is a synthetic successful ledger row for checking result persistence.
    # It does not certify a real model invocation or platform acquisition.
    session.execute(
        text(
            "INSERT INTO ai_calls "
            "(id,owner_id,purpose,provider,model,prompt_version,input_fingerprint,status,"
            "input_tokens,cached_input_tokens,output_tokens,reasoning_output_tokens,"
            "duration_ms,created_at) VALUES (:id,:owner,'analysis.annotate','controlled',"
            "'controlled-local-result',:prompt,:fingerprint,'succeeded',0,0,0,0,0,:now)"
        ),
        {
            "id": call,
            "owner": owner,
            "prompt": ANALYSIS_PROMPT_VERSION,
            "fingerprint": bytes.fromhex(manifest.signature),
            "now": at,
        },
    )
    results = tuple(
        AnnotationWrite(
            content_version_id=post.content_version_id,
            ai_call_id=call,
            status=AnnotationStatus.ANNOTATED,
            result_state=AnnotationResultState.VALID,
            relevant=True,
            relevance_reason="受控相关性结论",
            sentiment=sentiment,
            summary=label,
        )
        for post in posts
    )
    arguments = dict(
        owner_id=owner,
        topic_id=topic_id,
        topic_rule_version=1,
        prompt_version=ANALYSIS_PROMPT_VERSION,
        posts={post.content_version_id: post for post in posts},
        results=results,
        created_at=at,
        input_manifest=manifest,
    )
    AnalysisService(session).persist_results_in_transaction(**arguments)
    return arguments


def annotations(session, owner):
    return tuple(
        session.scalars(
            select(ContentAnnotation)
            .where(ContentAnnotation.owner_id == owner)
            .order_by(ContentAnnotation.created_at, ContentAnnotation.id)
        )
    )


def revoke(session, owner, source_key):
    session.execute(
        text(
            "UPDATE source_access_policies SET enabled=false "
            "WHERE owner_id=:owner AND source_key=:key"
        ),
        {"owner": owner, "key": source_key},
    )


def test_same_version_independent_manifests_results_and_exact_replay_coexist(engine):
    with Session(engine, expire_on_commit=False) as session:
        owner, _, _, a, b = aliases(session)
        with session.begin():
            identifier = topic(session, owner)
            manifest_a, manifest_b = freeze(session, owner, a), freeze(session, owner, b)
            assert manifest_a.signature != manifest_b.signature
            first = persist(session, owner, identifier, manifest_a, label="来源 A 的独立摘要")
            second = persist(session, owner, identifier, manifest_b, label="来源 B 的独立摘要")
            AnalysisService(session).persist_results_in_transaction(**first)
            AnalysisService(session).persist_results_in_transaction(**second)
            rows = annotations(session, owner)
            assert len(rows) == 2
            assert {row.content_version_id for row in rows} == {a[1]}
            assert {row.input_signature for row in rows} == {
                manifest_a.signature,
                manifest_b.signature,
            }
            assert {row.summary for row in rows} == {"来源 A 的独立摘要", "来源 B 的独立摘要"}
            assert {row.input_manifest["post_observations"][str(a[1])] for row in rows} == {
                str(a[2]),
                str(b[2]),
            }
            assert {
                view.id
                for view in load_content_annotations_in_transaction(
                    session, owner_id=owner, content_id=a[0], readable_version_ids={a[1]}, now=NOW
                )
            } == {row.id for row in rows}


def test_modern_job_operation_freezes_input_signature_and_retry_without_reinterpreting_scope(
    engine,
):
    with Session(engine) as session:
        owner, _, _, a, b = aliases(session)
        with session.begin():
            identifier = topic(session, owner)
            manifest_a, manifest_b = freeze(session, owner, a), freeze(session, owner, b)
            identity = dict(
                topic_id=identifier,
                topic_rule_version=1,
                content_version_ids=(a[1],),
                prompt_version=ANALYSIS_PROMPT_VERSION,
            )
            operation = analysis_operation_id(**identity, input_signature=manifest_a.signature)
            assert operation == analysis_operation_id(
                **identity, input_signature=manifest_a.signature
            )
            assert operation != analysis_operation_id(
                **identity, input_signature=manifest_b.signature
            )
            assert operation != analysis_operation_id(
                **identity, input_signature=manifest_a.signature, retry_index=1
            )
            assert operation != analysis_operation_id(**identity)
            post = load_post_versions_for_analysis(
                session,
                owner_id=owner,
                content_version_ids={a[1]},
                readable_at=NOW,
                selected_observations=manifest_a.post_observations,
            )[0]
            scope = AnalysisJobScope(
                **identity,
                prompt_items=(
                    AnalysisPromptItem(
                        content_id=post.content_id,
                        content_version_id=post.content_version_id,
                        title=post.title,
                        body=post.body,
                        comments=(),
                        comment_version_ids=(),
                    ),
                ),
                input_manifest=manifest_a,
            )
            accepted = JobService(session, clock=lambda: NOW).accept_in_transaction(
                owner_id=owner,
                command=JobAcceptanceInput(
                    operation_id=operation,
                    kind="analysis.annotate",
                    observation=JobObservationContext(
                        configuration_ref=f"topic:{identifier}",
                        configuration_version=1,
                    ),
                    scope=scope.to_job_scope(),
                ),
            )
            message = JobAcceptedMessage(
                schema_version=2,
                message_id=uuid4(),
                event_type="job.accepted.v2",
                job_id=accepted.id,
                owner_id=owner,
                operation_id=operation,
                kind="analysis.annotate",
                configuration_ref=f"topic:{identifier}",
                configuration_version=1,
            )
            executor = AnalysisAnnotateExecutor(
                sessionmaker(engine),
                Settings(_env_file=None, database_url=os.environ["HOTKEY_TEST_DATABASE_URL"]),
                clock=lambda: NOW,
            )
            loaded, _, posts, items = executor._load_execution_in_transaction(session, message)
            assert loaded.input_manifest == manifest_a
            assert posts[a[1]].observation_id == a[2] and len(items) == 1
            session.execute(
                text("UPDATE jobs SET operation_id=:operation WHERE id=:id"),
                {"operation": uuid4(), "id": accepted.id},
            )
            session.expire_all()
            with pytest.raises(JobExecutionFailure) as failure:
                executor._load_execution_in_transaction(session, message)
            assert failure.value.error_code == "analysis_scope_mismatch"
            assert (
                session.scalar(
                    text("SELECT count(*) FROM ai_calls WHERE owner_id=:owner"), {"owner": owner}
                )
                == 0
            )


def test_revoked_alias_cannot_supply_annotations_reports_or_event_refs_independent_alias_survives(
    engine,
):
    with Session(engine, expire_on_commit=False) as session:
        owner, profile_a, _, a, b = aliases(session)
        with session.begin():
            identifier = topic(session, owner)
            manifest_a, manifest_b = freeze(session, owner, a), freeze(session, owner, b)
            persist(session, owner, identifier, manifest_b, label="独立 B 摘要")
            persist(
                session,
                owner,
                identifier,
                manifest_a,
                label="较新 A 摘要",
                at=NOW + timedelta(seconds=1),
            )
            rows = {row.input_signature: row for row in annotations(session, owner)}
            row_a, row_b = rows[manifest_a.signature], rows[manifest_b.signature]
            fixed = {row_a.id: (a[1], a[2]), row_b.id: (b[1], b[2])}
            assert relevant_event_annotation_ids_in_transaction(
                session,
                owner_id=owner,
                topic_id=identifier,
                topic_rule_version=1,
                references=fixed,
                now=NOW,
            ) == frozenset(fixed)
            for overrides in (
                {"owner_id": uuid4()},
                {"topic_id": uuid4()},
                {"topic_rule_version": 2},
                {"references": {row_a.id: (a[1], b[2]), row_b.id: (b[1], a[2])}},
                {"references": {row_a.id: (uuid4(), a[2])}},
                {"references": {uuid4(): (a[1], a[2])}},
            ):
                assert not relevant_event_annotation_ids_in_transaction(
                    session,
                    **{
                        "owner_id": owner,
                        "topic_id": identifier,
                        "topic_rule_version": 1,
                        "references": fixed,
                        "now": NOW,
                        **overrides,
                    },
                )
            assert readable_annotation_ids_in_transaction(
                session, annotations=(row_a, row_b), now=NOW
            ) == {row_a.id, row_b.id}
            before = list_relevant_event_annotation_refs_in_transaction(
                session, since=NOW, now=NOW + timedelta(seconds=1), version_ids=(a[1],)
            )
            assert len(before.items) == 1 and before.items[0].observation_id == a[2]
            revoke(session, owner, profile_a.source_key)
            assert relevant_event_annotation_ids_in_transaction(
                session,
                owner_id=owner,
                topic_id=identifier,
                topic_rule_version=1,
                references=fixed,
                now=NOW,
            ) == frozenset({row_b.id})
            assert readable_annotation_ids_in_transaction(
                session, annotations=(row_a, row_b), now=NOW
            ) == {row_b.id}
            assert not annotation_inputs_readable_in_transaction(session, annotation=row_a, now=NOW)
            assert annotation_inputs_readable_in_transaction(session, annotation=row_b, now=NOW)
            assert [
                view.id
                for view in load_content_annotations_in_transaction(
                    session, owner_id=owner, content_id=a[0], readable_version_ids={a[1]}, now=NOW
                )
            ] == [row_b.id]
            for row, allowed in ((row_a, False), (row_b, True)):
                assert (
                    report_annotations_readable_in_transaction(
                        session,
                        owner_id=owner,
                        topic_id=identifier,
                        annotation_ids=(row.id,),
                        content_version_ids=(a[1],),
                        now=NOW,
                    )
                    is allowed
                )
            assert not report_annotations_readable_in_transaction(
                session,
                owner_id=owner,
                topic_id=identifier,
                annotation_ids=(row_a.id, row_b.id),
                content_version_ids=(a[1],),
                now=NOW,
            )
            with pytest.raises(ApplicationError, match="editorial_material_unavailable"):
                load_report_annotation_observation_ids_in_transaction(
                    session,
                    owner_id=owner,
                    topic_id=identifier,
                    annotation_ids=(row_a.id,),
                    now=NOW,
                )
            assert load_report_annotation_observation_ids_in_transaction(
                session, owner_id=owner, topic_id=identifier, annotation_ids=(row_b.id,), now=NOW
            ) == (b[2],)
            after = list_relevant_event_annotation_refs_in_transaction(
                session, since=NOW, now=NOW + timedelta(seconds=1), version_ids=(a[1],)
            )
            assert len(after.items) == 1
            assert (after.items[0].observation_id, after.items[0].input_observation_ids) == (
                b[2],
                (b[2],),
            )


@pytest.mark.parametrize("withdraw", [0, 1])
def test_one_withdrawn_input_blocks_all_results_from_a_two_post_prompt_batch(engine, withdraw):
    with Session(engine, expire_on_commit=False) as session:
        first, owner, profile_a = configured(session)
        second, _, profile_b = configured(
            session,
            owner_id=owner,
            route="/threads/search/sample/serpType=recent",
            mode="platform_keyword",
        )
        _, a = collect(session, first, owner, profile_a)
        _, b = collect(
            session,
            second,
            owner,
            profile_b,
            url="https://www.threads.com/t/Other_Post",
            body="另一篇独立原帖",
        )
        with session.begin():
            identifier = topic(session, owner)
            manifest = freeze(session, owner, b, a)
            independent = (freeze(session, owner, a), freeze(session, owner, b))
            batches = (manifest, *independent)
            assert analysis_observation_manifests_readable_in_transaction(
                session, owner_id=owner, manifests=batches, now=NOW
            ) == {item.signature: True for item in batches}
            assert analysis_observation_manifests_readable_in_transaction(
                session, owner_id=uuid4(), manifests=batches, now=NOW
            ) == {item.signature: False for item in batches}
            assert manifest.input_observation_ids == tuple(sorted((a[2], b[2]), key=str))
            assert freeze(session, owner, a, b).signature == manifest.signature
            persist(session, owner, identifier, manifest, label="整批模型摘要")
            rows = annotations(session, owner)
            assert len(rows) == 2 and {row.input_signature for row in rows} == {manifest.signature}
            frozen_classifications = {
                row.id: (
                    row.content_version_id,
                    manifest.post_observations[row.content_version_id],
                )
                for row in rows
            }
            assert relevant_event_annotation_ids_in_transaction(
                session,
                owner_id=owner,
                topic_id=identifier,
                topic_rule_version=1,
                references=frozen_classifications,
                now=NOW,
            ) == frozenset(frozen_classifications)
            assert all(
                annotation_inputs_readable_in_transaction(session, annotation=row, now=NOW)
                for row in rows
            )
            revoke(session, owner, (profile_a, profile_b)[withdraw].source_key)
            assert not relevant_event_annotation_ids_in_transaction(
                session,
                owner_id=owner,
                topic_id=identifier,
                topic_rule_version=1,
                references=frozen_classifications,
                now=NOW,
            )
            assert analysis_observation_manifests_readable_in_transaction(
                session, owner_id=owner, manifests=batches, now=NOW
            ) == {
                manifest.signature: False,
                independent[withdraw].signature: False,
                independent[1 - withdraw].signature: True,
            }
            with pytest.raises(ApplicationError, match="editorial_material_unavailable"):
                require_analysis_observation_inputs_in_transaction(
                    session, owner_id=owner, manifest=manifest, now=NOW
                )
            assert all(
                not annotation_inputs_readable_in_transaction(session, annotation=row, now=NOW)
                for row in rows
            )
            retained = (b, a)[withdraw]
            assert report_inputs_readable_in_transaction(
                session,
                owner_id=owner,
                content_version_ids=(retained[1],),
                observation_ids=(retained[2],),
                now=NOW,
            )
            assert (
                load_content_annotations_in_transaction(
                    session,
                    owner_id=owner,
                    content_id=retained[0],
                    readable_version_ids={retained[1]},
                    now=NOW,
                )
                == []
            )
            assert not report_annotations_readable_in_transaction(
                session,
                owner_id=owner,
                topic_id=identifier,
                annotation_ids=tuple(row.id for row in rows),
                content_version_ids=(a[1], b[1]),
                now=NOW,
            )
            assert not list_relevant_event_annotation_refs_in_transaction(
                session, since=NOW, version_ids=(a[1], b[1]), now=NOW
            ).items
            facts = load_negative_alert_facts_in_transaction(
                session,
                owner_id=owner,
                topic_id=identifier,
                topic_rule_version=1,
                start=NOW,
                end=NOW + timedelta(seconds=1),
                now=NOW,
            )
            assert facts.value is None and facts.reason == "alert_sentiment_missing"


@pytest.mark.parametrize(
    "change", ["owner", "version", "map", "comment_kind", "extra_closure", "dto_observation"]
)
def test_wrong_owner_version_map_or_post_witness_cannot_persist_a_result(engine, change):
    with Session(engine, expire_on_commit=False) as session:
        owner, _, profile_b, a, b = aliases(session)
        if change == "comment_kind":
            _, other_post = collect(
                session,
                EditorialSourceService(session, clock=lambda: NOW),
                owner,
                profile_b,
                url="https://www.threads.com/t/Another_Post",
                body="真实存在的另一条帖子观察不能伪称评论",
            )
        with session.begin():
            manifest = freeze(session, owner, a)
            if change == "dto_observation":
                identifier = topic(session, owner)
                args = persist(session, owner, identifier, manifest, label="原观察结果")
                before = {row.id for row in annotations(session, owner)}
                args["posts"] = {
                    a[1]: args["posts"][a[1]].model_copy(update={"observation_id": b[2]})
                }
                with pytest.raises(ApplicationError, match="editorial_material_unavailable"):
                    AnalysisService(session).persist_results_in_transaction(**args)
                assert {row.id for row in annotations(session, owner)} == before
                return
            supplied_owner = owner
            if change == "owner":
                supplied_owner = uuid4()
            elif change == "version":
                manifest = AnalysisObservationManifest(
                    post_observations={uuid4(): a[2]}, input_observation_ids=(a[2],)
                )
            elif change == "map":
                invented_observation = uuid4()
                manifest = AnalysisObservationManifest(
                    post_observations={a[1]: invented_observation},
                    input_observation_ids=(invented_observation,),
                )
            elif change == "comment_kind":
                manifest = manifest.model_copy(
                    update={
                        "comment_observations": {other_post[1]: other_post[2]},
                        "input_observation_ids": tuple(sorted((a[2], other_post[2]), key=str)),
                    }
                )
            elif change == "extra_closure":
                manifest = manifest.model_copy(
                    update={"input_observation_ids": tuple(sorted((a[2], uuid4()), key=str))}
                )
            with pytest.raises(ApplicationError, match="editorial_material_unavailable"):
                require_analysis_observation_inputs_in_transaction(
                    session, owner_id=supplied_owner, manifest=manifest, now=NOW
                )
            assert not annotations(session, owner)


def test_physical_cleanup_removes_only_results_with_the_withdrawn_alias_input(engine):
    with Session(engine, expire_on_commit=False) as session:
        owner, _, profile_b, a, b = aliases(session)
        _, other_post = collect(
            session,
            EditorialSourceService(session, clock=lambda: NOW),
            owner,
            profile_b,
            url="https://www.threads.com/t/Another_Post",
            body="仍有读取许可的另一条原帖",
        )
        with session.begin():
            identifier = topic(session, owner)
            manifest_a, manifest_b = freeze(session, owner, a), freeze(session, owner, b)
            persist(session, owner, identifier, manifest_a, label="将删除的 A 结果")
            persist(session, owner, identifier, manifest_b, label="应保留的独立 B 结果")
            batch = freeze(session, owner, a, other_post)
            persist(session, owner, identifier, batch, label="依赖 A 的整批结果")
            before = annotations(session, owner)
            assert len(before) == 4
            a_id = next(row.id for row in before if row.input_signature == manifest_a.signature)
            b_id = next(row.id for row in before if row.input_signature == manifest_b.signature)
            batch_ids = tuple(row.id for row in before if row.input_signature == batch.signature)
            purge_observation_dependants_in_transaction(
                session, owner_id=owner, observation_id=a[2], now=NOW
            )
            session.flush()
            assert session.get(ContentObservation, a[2]) is None
            assert session.get(ContentObservation, b[2]) is not None
            assert session.get(ContentVersion, b[1]) is not None
            assert session.get(ContentObservation, other_post[2]) is not None
            assert session.get(ContentVersion, other_post[1]) is not None
            rows = annotations(session, owner)
            assert [row.id for row in rows] == [b_id]
            assert rows[0].summary == "应保留的独立 B 结果"
            assert not report_annotations_readable_in_transaction(
                session,
                owner_id=owner,
                topic_id=identifier,
                annotation_ids=(a_id, *batch_ids),
                content_version_ids=(a[1],),
                now=NOW,
            )
            assert report_annotations_readable_in_transaction(
                session,
                owner_id=owner,
                topic_id=identifier,
                annotation_ids=(b_id,),
                content_version_ids=(b[1],),
                now=NOW,
            )


def test_report_uses_readable_independent_alias_when_newer_same_version_alias_is_revoked(engine):
    with Session(engine, expire_on_commit=False) as session:
        _, owner, profile_a = configured(session)
        service_b, _, profile_b = configured(
            session,
            owner_id=owner,
            route="/threads/search/sample/serpType=recent",
            mode="platform_keyword",
        )
        topics = MonitorTopicService(session, clock=lambda: NOW)
        selected = topics.create_topic(
            owner_id=owner,
            command=MonitorTopicCreateInput(
                name="Independent source summaries",
                match_any=["original"],
                match_all=[],
                exclude=[],
                editorial_profile_ids=[profile_a.id, profile_b.id],
            ),
        )
        selected = topics.resume_topic(owner_id=owner, topic_id=selected.id)
        _, b = collect(session, service_b, owner, profile_b)
        _, a = collect(
            session,
            EditorialSourceService(session, clock=lambda: NOW + timedelta(seconds=1)),
            owner,
            profile_a,
        )
        assert a[:2] == b[:2]
        with session.begin():
            persist(session, owner, selected.id, freeze(session, owner, b), label="合法独立 B 摘要")
            persist(
                session,
                owner,
                selected.id,
                freeze(session, owner, a),
                label="将撤权的较新 A 摘要",
                at=NOW + timedelta(seconds=1),
            )
            revoke(session, owner, profile_a.source_key)
            dataset = ReportService(
                session, clock=lambda: NOW + timedelta(seconds=2)
            )._load_dataset(
                owner_id=owner,
                topic_id=selected.id,
                window_start=NOW - timedelta(days=1),
                window_end=NOW + timedelta(seconds=3),
                cutoff_at=NOW + timedelta(seconds=2),
            )
            assert len(dataset.posts) == 1
            assert dataset.posts[0].observation_id == b[2]
            assert dataset.posts[0].summary == "合法独立 B 摘要"


def test_m4_deduplicates_aliases_and_rechecks_the_exact_selected_analysis_inputs(engine):
    with Session(engine, expire_on_commit=False) as session:
        owner, profile_a, _, a, b = aliases(session)
        with session.begin():
            identifier = topic(session, owner)
            manifest_a, manifest_b = freeze(session, owner, a), freeze(session, owner, b)
            persist(session, owner, identifier, manifest_b, label="独立中性 B 结论")
            persist(
                session,
                owner,
                identifier,
                manifest_a,
                label="较新负面 A 结论",
                sentiment=Sentiment.NEGATIVE,
                at=NOW + timedelta(seconds=1),
            )
            options = dict(
                owner_id=owner,
                topic_id=identifier,
                topic_rule_version=1,
                start=NOW,
                end=NOW + timedelta(seconds=2),
                now=NOW + timedelta(seconds=2),
            )
            before = load_negative_alert_facts_in_transaction(session, **options)
            assert before.value == 1 and len(before.manifest["inputs"]) == 1
            assert before.manifest["inputs"][0]["analysis_input_signature"] == manifest_a.signature
            assert negative_alert_inputs_readable_in_transaction(
                session, owner_id=owner, manifest=before.manifest, now=options["now"]
            )
            revoke(session, owner, profile_a.source_key)
            assert not negative_alert_inputs_readable_in_transaction(
                session, owner_id=owner, manifest=before.manifest, now=options["now"]
            )
            after = load_negative_alert_facts_in_transaction(session, **options)
            assert after.value == 0 and len(after.manifest["inputs"]) == 1
            assert after.manifest["inputs"][0]["analysis_input_signature"] == manifest_b.signature
            assert negative_alert_inputs_readable_in_transaction(
                session, owner_id=owner, manifest=after.manifest, now=options["now"]
            )


def test_modern_scope_does_not_accept_comment_text_without_frozen_comment_roots(engine):
    with Session(engine) as session:
        owner, _, _, a, _ = aliases(session)
        with session.begin():
            manifest = freeze(session, owner, a)
            post = load_post_versions_for_analysis(
                session,
                owner_id=owner,
                content_version_ids={a[1]},
                selected_observations=manifest.post_observations,
                readable_at=NOW,
            )[0]
            with pytest.raises(ValidationError):
                AnalysisJobScope(
                    topic_id=uuid4(),
                    topic_rule_version=1,
                    prompt_version=ANALYSIS_PROMPT_VERSION,
                    content_version_ids=(a[1],),
                    prompt_items=(
                        AnalysisPromptItem(
                            content_id=a[0],
                            content_version_id=a[1],
                            title=post.title,
                            body=post.body,
                            comments=("没有对应冻结观察的评论文本",),
                            comment_version_ids=None,
                        ),
                    ),
                    input_manifest=manifest,
                )


def legacy_result(case):
    with case.sessions() as session, session.begin():
        accepted = AnalysisService(
            session,
            settings=Settings(_env_file=None, database_url=os.environ["HOTKEY_TEST_DATABASE_URL"]),
        ).enqueue_due_batches_in_transaction(
            owner_id=case.owner_id, topic_id=case.topic_id, now=case.now
        )
        assert len(accepted) == 1
        job_id = accepted[0].id
    with case.sessions() as session, session.begin():
        raw = session.scalar(text("SELECT scope FROM jobs WHERE id=:id"), {"id": job_id})
        legacy_raw = dict(raw)
        legacy_raw.pop("input_manifest")
        scope = AnalysisJobScope.from_job_scope(legacy_raw)
        assert scope.prompt_items[0].comments == ("原评论",)
        assert scope.prompt_items[0].comment_version_ids
        operation = analysis_operation_id(
            topic_id=scope.topic_id,
            topic_rule_version=scope.topic_rule_version,
            content_version_ids=scope.content_version_ids,
            prompt_version=scope.prompt_version,
            retry_index=scope.retry_index,
        )
        session.execute(
            text(
                "UPDATE jobs SET scope=CAST(:scope AS jsonb),operation_id=:operation WHERE id=:id"
            ),
            {"id": job_id, "scope": json.dumps(legacy_raw), "operation": operation},
        )
        assert analysis_scope_inputs_readable_in_transaction(
            session, owner_id=case.owner_id, scope=scope, now=case.now
        )
    call_id = uuid4()
    _seed_ai_call(case, call_id)
    with case.sessions() as session, session.begin():
        session.execute(
            text("UPDATE ai_calls SET job_id=:job WHERE id=:id"), {"job": job_id, "id": call_id}
        )
        posts = load_post_versions_for_analysis(
            session,
            owner_id=case.owner_id,
            content_version_ids={case.version_id},
            readable_at=case.now,
        )
        AnalysisService(session).persist_results_in_transaction(
            owner_id=case.owner_id,
            topic_id=case.topic_id,
            topic_rule_version=1,
            prompt_version=ANALYSIS_PROMPT_VERSION,
            posts={post.content_version_id: post for post in posts},
            results=(
                AnnotationWrite(
                    content_version_id=case.version_id,
                    relevant=True,
                    relevance_reason="受控旧任务结论",
                    sentiment=Sentiment.NEUTRAL,
                    summary="曾包含原评论事实的历史摘要",
                    ai_call_id=call_id,
                    status=AnnotationStatus.ANNOTATED,
                    result_state=AnnotationResultState.VALID,
                ),
            ),
            created_at=case.now,
            input_manifest=None,
        )
        row_id = annotations(session, case.owner_id)[0].id
    return job_id, scope, call_id, row_id


def test_legacy_annotation_does_not_outlive_its_original_comment_permission(analysis_case):
    case = analysis_case
    _, scope, _, row_id = legacy_result(case)
    with case.sessions() as session, session.begin():
        row = session.get(ContentAnnotation, row_id)
        assert annotation_inputs_readable_in_transaction(session, annotation=row, now=case.now)
    _make_unreadable(case, case.comment_id, "expired")
    with case.sessions() as session, session.begin():
        assert not analysis_scope_inputs_readable_in_transaction(
            session, owner_id=case.owner_id, scope=scope, now=case.now
        )
        assert load_post_versions_for_analysis(
            session,
            owner_id=case.owner_id,
            content_version_ids={case.version_id},
            readable_at=case.now,
        )
        row = session.get(ContentAnnotation, row_id)
        assert not annotation_inputs_readable_in_transaction(session, annotation=row, now=case.now)


@pytest.mark.parametrize(
    "change", ["missing_job", "owner", "purpose", "prompt", "status", "incomplete_scope"]
)
def test_legacy_call_and_original_scope_must_prove_their_actual_authority(analysis_case, change):
    case = analysis_case
    job_id, scope, call_id, row_id = legacy_result(case)
    with case.sessions() as session, session.begin():
        assert (
            load_legacy_analysis_call_job_in_transaction(
                session,
                owner_id=case.owner_id,
                ai_call_id=call_id,
                prompt_version=ANALYSIS_PROMPT_VERSION,
            )
            == job_id
        )
        if change == "owner":
            assert (
                load_legacy_analysis_call_job_in_transaction(
                    session,
                    owner_id=uuid4(),
                    ai_call_id=call_id,
                    prompt_version=ANALYSIS_PROMPT_VERSION,
                )
                is None
            )
            return
        if change == "missing_job":
            session.execute(text("UPDATE ai_calls SET job_id=NULL WHERE id=:id"), {"id": call_id})
        elif change == "purpose":
            session.execute(
                text("UPDATE ai_calls SET purpose='editorial.analyze' WHERE id=:id"),
                {"id": call_id},
            )
        elif change == "prompt":
            session.execute(
                text("UPDATE ai_calls SET prompt_version='other-prompt' WHERE id=:id"),
                {"id": call_id},
            )
        elif change == "status":
            session.execute(
                text("UPDATE ai_calls SET status='unknown',failure_code='timeout' WHERE id=:id"),
                {"id": call_id},
            )
        elif change == "incomplete_scope":
            raw = scope.to_job_scope()
            items = json.loads(raw["prompt_items"])
            for item in items:
                item.pop("comment_version_ids")
            raw["prompt_items"] = json.dumps(items)
            session.execute(
                text("UPDATE jobs SET scope=CAST(:scope AS jsonb) WHERE id=:id"),
                {"id": job_id, "scope": json.dumps(raw)},
            )
        if change != "incomplete_scope":
            assert (
                load_legacy_analysis_call_job_in_transaction(
                    session,
                    owner_id=case.owner_id,
                    ai_call_id=call_id,
                    prompt_version=ANALYSIS_PROMPT_VERSION,
                )
                is None
            )
        row = session.get(ContentAnnotation, row_id)
        assert not annotation_inputs_readable_in_transaction(session, annotation=row, now=case.now)
