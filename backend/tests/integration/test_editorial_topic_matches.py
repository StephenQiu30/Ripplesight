from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker
from tests.conftest import authenticate_test_client
from tests.integration.test_editorial_source_profiles import NOW, begin, job, material, page, setup

from content.export_reading import freeze_export_content_in_transaction
from content.models import ContentObservation, ContentRecord, ContentTopicMatch, ContentVersion
from content.report_reading import report_inputs_readable_in_transaction
from content.services import (
    ContentObservationCleanup,
    ContentService,
    load_post_versions_for_analysis_scan,
)
from content.topic_matches import readable_editorial_topic_matches_in_transaction
from content.version_inputs import (
    save_version_inputs_in_transaction,
    version_inputs_readable_in_transaction,
)
from core.config import Settings
from core.errors import ApplicationError
from evidence.schemas import CleanupTargetKind, DeletionReason
from evidence.services import CleanupProcessor, LifecycleService
from main import create_app
from monitors.schemas import MonitorTopicCreateInput, MonitorTopicUpdateInput
from monitors.services import MonitorTopicService
from reports.services import ReportService


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


def _topic(session: Session, owner: UUID, profile_id: UUID, keyword: str = "model"):
    service = MonitorTopicService(session, clock=lambda: NOW)
    topic = service.create_topic(
        owner_id=owner,
        command=MonitorTopicCreateInput(
            name=f"Topic {keyword}",
            match_any=[keyword],
            match_all=[],
            exclude=[],
            editorial_profile_ids=[profile_id],
        ),
    )
    assert topic.readiness_status == "ready"
    return service.resume_topic(owner_id=owner, topic_id=topic.id)


def _ingest(session: Session, service, owner: UUID, profile, *, title: str = "New model"):
    accepted, operation_id = job(session, owner, profile)
    prepared = begin(service, owner, profile, accepted, operation_id)
    service.stage_page(
        owner_id=owner,
        run_id=prepared.result.run_id,
        page=page(material(title)),
    )
    result = service.apply_page(owner_id=owner, run_id=prepared.result.run_id)
    assert result.status == "succeeded"
    return accepted


def test_one_original_ingest_matches_two_topics_and_all_consumers_use_frozen_version(engine):
    with Session(engine, expire_on_commit=False) as session:
        service, owner, profile, _ = setup(session)
        first = _topic(session, owner, profile.id, "model")
        second = _topic(session, owner, profile.id, "new")
        accepted = _ingest(session, service, owner, profile)
        with session.begin():
            matches = list(session.scalars(select(ContentTopicMatch)))
            assert len(matches) == 2
            assert {match.topic_id for match in matches} == {first.id, second.id}
            assert {match.job_id for match in matches} == {accepted.id}
            assert session.scalar(text("SELECT count(*) FROM content_records")) == 1
            assert session.scalar(text("SELECT count(*) FROM content_observations")) == 1
            assert session.scalar(text("SELECT count(*) FROM jobs")) == 1
            assert session.scalar(text("SELECT count(*) FROM monitor_schedules")) == 0
            frozen_version = matches[0].content_version_id
            content_id = matches[0].content_id
            for topic in (first, second):
                posts = load_post_versions_for_analysis_scan(
                    session,
                    owner_id=owner,
                    topic_id=topic.id,
                    topic_rule_version=topic.current_version,
                    source_keys=(),
                    as_of=NOW + timedelta(seconds=1),
                    readable_at=NOW,
                )
                assert [post.content_version_id for post in posts] == [frozen_version]
                dataset = ReportService(session, clock=lambda: NOW)._load_dataset(
                    owner_id=owner,
                    topic_id=topic.id,
                    window_start=NOW - timedelta(days=1),
                    window_end=NOW + timedelta(seconds=1),
                    cutoff_at=NOW,
                )
                assert [post.content_version_id for post in dataset.posts] == [frozen_version]
                assert dataset.posts[0].body == "Full controlled original source content"
        content = ContentService(session, clock=lambda: NOW)
        for topic in (first, second):
            listing = content.list_contents(
                owner_id=owner, topic_id=topic.id, cursor=None, limit=20
            )
            assert [item.id for item in listing[0]] == [content_id]
            assert listing[0][0].latest_observation.content_version.id == frozen_version
        detail = content.get_content(owner_id=owner, content_id=content_id)
        assert {item.topic_id for item in detail.analysis_topics} == {first.id, second.id}
        assert detail.source_name == profile.name


def test_rule_and_selection_changes_freeze_history_pause_stops_new_matches(engine):
    with Session(engine, expire_on_commit=False) as session:
        service, owner, profile, _ = setup(session)
        topic = _topic(session, owner, profile.id)
        _ingest(session, service, owner, profile)
        topics = MonitorTopicService(session, clock=lambda: NOW)
        changed = topics.update_topic(
            owner_id=owner,
            topic_id=topic.id,
            command=MonitorTopicUpdateInput(
                expected_version=1,
                name=topic.name,
                match_any=["unmatched"],
                match_all=[],
                exclude=[],
                editorial_profile_ids=[profile.id],
            ),
        )
        assert changed.current_version == 2
        _ingest(session, service, owner, profile, title="Another model")
        with session.begin():
            assert session.scalar(text("SELECT count(*) FROM content_topic_matches")) == 1
            old = readable_editorial_topic_matches_in_transaction(
                session, owner_id=owner, topic_id=topic.id, topic_rule_version=1, now=NOW
            )
            assert len(old) == 1
            assert not readable_editorial_topic_matches_in_transaction(
                session, owner_id=owner, topic_id=topic.id, topic_rule_version=2, now=NOW
            )
            assert len(list(session.scalars(select(ContentVersion)))) == 2
        # A later unmatched version cannot replace the historical matched version in a topic.
        listing = ContentService(session, clock=lambda: NOW).list_contents(
            owner_id=owner, topic_id=topic.id, cursor=None, limit=20
        )
        assert listing[0][0].latest_observation.content_version.id == old[0].content_version_id
        topics.pause_topic(owner_id=owner, topic_id=topic.id)
        _ingest(session, service, owner, profile, title="unmatched")
        with session.begin():
            assert session.scalar(text("SELECT count(*) FROM content_topic_matches")) == 1
        with session.begin():
            session.execute(
                text("UPDATE editorial_source_profiles SET enabled=false WHERE id=:id"),
                {"id": profile.id},
            )
        # Ordinary profile pause preserves lawful fixed history. Unavailable sources can be removed.
        assert ContentService(session, clock=lambda: NOW).list_contents(
            owner_id=owner, topic_id=topic.id, cursor=None, limit=20
        )[0]
        cancelled = topics.update_topic(
            owner_id=owner,
            topic_id=topic.id,
            command=MonitorTopicUpdateInput(
                expected_version=2,
                name=topic.name,
                match_any=["unmatched"],
                match_all=[],
                exclude=[],
                editorial_profile_ids=[],
            ),
        )
        assert cancelled.current_version == 3 and cancelled.editorial_profile_ids == []


def test_actual_input_all_blocks_content_analysis_and_report_when_one_policy_revoked(engine):
    with Session(engine, expire_on_commit=False) as session:
        first_service, owner, first_profile, _ = setup(session)
        second_service, _, second_profile, _ = setup(session, owner_id=owner)
        topic = _topic(session, owner, first_profile.id)
        _ingest(session, first_service, owner, first_profile)
        _ingest(session, second_service, owner, second_profile)
        with session.begin():
            first_match = session.scalar(select(ContentTopicMatch))
            second_observation = session.scalar(
                select(ContentObservation)
                .join(ContentRecord, ContentRecord.id == ContentObservation.content_id)
                .where(ContentRecord.source_key == second_profile.source_key)
            )
            assert first_match is not None and second_observation is not None
            session.execute(
                text(
                    "UPDATE content_observations SET input_basis=NULL, source_key=NULL, "
                    "source_native_scope=NULL, source_external_id=NULL, "
                    "source_identity_basis=NULL, "
                    "editorial_profile_id=NULL, native_identity_proof=NULL WHERE id=:id"
                ),
                {"id": first_match.observation_id},
            )
            session.expire_all()
            dependencies = (first_match.observation_id, second_observation.id)
            save_version_inputs_in_transaction(
                session,
                owner_id=owner,
                content_version_id=first_match.content_version_id,
                observation_ids=dependencies,
            )
            save_version_inputs_in_transaction(
                session,
                owner_id=owner,
                content_version_id=first_match.content_version_id,
                observation_ids=dependencies,
            )
            assert version_inputs_readable_in_transaction(
                session,
                owner_id=owner,
                content_version_ids=(first_match.content_version_id,),
                now=NOW,
            )
            with pytest.raises(ApplicationError, match="idempotency_conflict"):
                save_version_inputs_in_transaction(
                    session,
                    owner_id=owner,
                    content_version_id=first_match.content_version_id,
                    observation_ids=(first_match.observation_id,),
                )
            session.execute(
                text("UPDATE source_access_policies SET enabled=false WHERE source_key=:key"),
                {"key": second_profile.source_key},
            )
        with session.begin():
            assert not version_inputs_readable_in_transaction(
                session,
                owner_id=owner,
                content_version_ids=(first_match.content_version_id,),
                now=NOW,
            )
            assert not report_inputs_readable_in_transaction(
                session,
                owner_id=owner,
                content_version_ids=(first_match.content_version_id,),
                observation_ids=(first_match.observation_id,),
                now=NOW,
            )
            assert not load_post_versions_for_analysis_scan(
                session,
                owner_id=owner,
                topic_id=topic.id,
                topic_rule_version=1,
                source_keys=(),
                readable_at=NOW,
            )
        assert not ContentService(session, clock=lambda: NOW).list_contents(
            owner_id=owner, topic_id=topic.id, cursor=None, limit=20
        )[0]
        with pytest.raises(ApplicationError, match="resource_not_found"):
            ContentService(session, clock=lambda: NOW).get_content(
                owner_id=owner, content_id=first_match.content_id
            )


def test_profile_selector_is_owner_scoped_and_real_get_is_read_only(engine):
    url = os.environ["HOTKEY_TEST_DATABASE_URL"]
    with TestClient(create_app(Settings(environment="test", database_url=url))) as client:
        owner = authenticate_test_client(client)
        with Session(engine, expire_on_commit=False) as session:
            _, _, profile, _ = setup(session, owner_id=owner)
            _, outsider, foreign_profile, _ = setup(session)
            topics = MonitorTopicService(session)
            with pytest.raises(ApplicationError, match="resource_not_found"):
                _topic(session, owner, foreign_profile.id)
            before = tuple(
                session.scalar(text(f"SELECT count(*) FROM {table}"))
                for table in ("jobs", "resource_usage_attempts", "content_topic_matches")
            )
            session.rollback()
            response = client.get("/api/topics/editorial-sources")
            assert response.status_code == 200, response.text
            assert "no-store" in response.headers["cache-control"]
            assert [row["profile_id"] for row in response.json()] == [str(profile.id)]
            assert response.json()[0]["query_mode"] == "feed_local_filter"
            assert response.json()[0]["selectable"] is True
            assert not {"route", "configuration", "secret", "owner_id"} & response.json()[0].keys()
            after = tuple(
                session.scalar(text(f"SELECT count(*) FROM {table}"))
                for table in ("jobs", "resource_usage_attempts", "content_topic_matches")
            )
            assert before == after
            session.rollback()
            assert (
                topics.list_editorial_sources(owner_id=outsider)[0].profile_id == foreign_profile.id
            )
        client.cookies.clear()
        assert client.get("/api/topics/editorial-sources").status_code == 401


def test_frozen_inputs_reject_other_owner_and_expiry_without_replacing_a_version(engine):
    with Session(engine, expire_on_commit=False) as session:
        service, owner, profile, _ = setup(session)
        _topic(session, owner, profile.id)
        _ingest(session, service, owner, profile)
        foreign_service, foreign_owner, foreign_profile, _ = setup(session)
        _ingest(session, foreign_service, foreign_owner, foreign_profile)
        with session.begin():
            match = session.scalar(select(ContentTopicMatch))
            outsider = session.scalar(
                select(ContentObservation).where(ContentObservation.owner_id == foreign_owner)
            )
            assert match is not None and outsider is not None
            with pytest.raises(ApplicationError, match="editorial_material_unavailable"):
                save_version_inputs_in_transaction(
                    session,
                    owner_id=owner,
                    content_version_id=match.content_version_id,
                    observation_ids=(outsider.id,),
                )
            save_version_inputs_in_transaction(
                session,
                owner_id=owner,
                content_version_id=match.content_version_id,
                observation_ids=(match.observation_id,),
            )
            assert not version_inputs_readable_in_transaction(
                session,
                owner_id=owner,
                content_version_ids=(match.content_version_id,),
                now=NOW + timedelta(days=31),
            )
            # A changed policy version cannot re-authorize the original frozen input by alias.
            session.execute(
                text("UPDATE source_access_policies SET policy_version=2 WHERE owner_id=:owner"),
                {"owner": owner},
            )
            assert not version_inputs_readable_in_transaction(
                session,
                owner_id=owner,
                content_version_ids=(match.content_version_id,),
                now=NOW,
            )


def test_original_cleanup_deletes_derived_chain_reports_and_matches_atomically(engine):
    sessions = sessionmaker(engine, expire_on_commit=False)
    with sessions() as session:
        service, owner, profile, _ = setup(session)
        topic = _topic(session, owner, profile.id)
        _ingest(session, service, owner, profile)
        with session.begin():
            feed_observation = session.scalar(select(ContentObservation))
            assert feed_observation is not None
        body_service = type(service)(session, clock=lambda: NOW + timedelta(seconds=1))
        _ingest(session, body_service, owner, profile, title="model with full body")
        with session.begin():
            body_observation = session.scalar(
                select(ContentObservation).where(ContentObservation.id != feed_observation.id)
            )
            assert body_observation is not None and body_observation.content_version_id is not None
            session.execute(
                text(
                    "UPDATE content_observations SET input_basis=NULL, source_key=NULL, "
                    "source_native_scope=NULL, source_external_id=NULL, "
                    "source_identity_basis=NULL, editorial_profile_id=NULL, "
                    "native_identity_proof=NULL WHERE id=:id"
                ),
                {"id": body_observation.id},
            )
            session.expire_all()
            save_version_inputs_in_transaction(
                session,
                owner_id=owner,
                content_version_id=body_observation.content_version_id,
                observation_ids=(feed_observation.id, body_observation.id),
            )
            report = ReportService(
                session, clock=lambda: NOW + timedelta(seconds=2)
            ).generate_daily_in_transaction(
                owner_id=owner,
                topic_id=topic.id,
                window_start=NOW - timedelta(days=1),
                window_end=NOW,
                cutoff_at=NOW + timedelta(seconds=2),
            )
            assert body_observation.content_version_id in report.input_manifest.content_version_ids
            assert report.generator == "template"
        foreign_service, outsider, foreign_profile, _ = setup(session)
        _ingest(session, foreign_service, outsider, foreign_profile)
        deletion = LifecycleService(session, clock=lambda: NOW).request_deletion(
            owner_id=owner,
            operation_id=uuid4(),
            resource_type="content_observation",
            resource_id=feed_observation.id,
            reason=DeletionReason.USER_REQUEST,
        )
        with pytest.raises(ApplicationError, match="resource_not_found"):
            ContentService(session, clock=lambda: NOW).get_content(
                owner_id=owner, content_id=feed_observation.content_id
            )
        with pytest.raises(ApplicationError, match="resource_not_found"):
            ReportService(session, clock=lambda: NOW).get_report(
                owner_id=owner, report_id=report.id
            )
    result = CleanupProcessor(
        sessions,
        handlers={
            CleanupTargetKind.POSTGRES_CONTENT_OBSERVATION: ContentObservationCleanup(
                sessions, clock=lambda: NOW
            )
        },
        clock=lambda: NOW,
    ).process_due(limit=10)
    assert result.failed == 0 and result.succeeded == 2
    with sessions() as session:
        completed = LifecycleService(session, clock=lambda: NOW).get_deletion(
            owner_id=owner, deletion_id=deletion.id
        )
        assert completed.status == "completed"
        for table in (
            "content_records",
            "content_versions",
            "content_observations",
            "content_version_inputs",
            "content_topic_matches",
            "editorial_source_material_receipts",
            "reports",
        ):
            assert (
                session.scalar(
                    text(f"SELECT count(*) FROM {table} WHERE owner_id=:owner"), {"owner": owner}
                )
                == 0
            )
        assert (
            session.scalar(
                text("SELECT count(*) FROM content_records WHERE owner_id=:owner"),
                {"owner": outsider},
            )
            == 1
        )


def test_export_freeze_requires_explicit_original_purpose_and_returns_fixed_nullable_metadata(
    engine,
):
    import json

    from connections.editorial_source_names import load_editorial_source_names_in_transaction

    with Session(engine, expire_on_commit=False) as session:
        service, owner, profile, _ = setup(session)
        _ingest(session, service, owner, profile)
        with session.begin():
            observation = session.scalar(select(ContentObservation))
            assert observation is not None and observation.content_version_id is not None
            with pytest.raises(ApplicationError, match="editorial_export_not_authorized"):
                freeze_export_content_in_transaction(
                    session,
                    owner_id=owner,
                    content_version_ids=(observation.content_version_id,),
                    now=NOW,
                )
            marker = "hotkey:personal-file-export:v1"
            fields = session.scalar(
                text("SELECT field_purposes FROM source_access_policies WHERE owner_id=:owner"),
                {"owner": owner},
            )
            session.execute(
                text(
                    "UPDATE source_access_policies SET processing_purpose=:marker, "
                    "field_purposes=CAST(:fields AS jsonb) WHERE owner_id=:owner"
                ),
                {
                    "marker": marker,
                    "fields": json.dumps(dict.fromkeys(fields, marker)),
                    "owner": owner,
                },
            )
            frozen = freeze_export_content_in_transaction(
                session,
                owner_id=owner,
                content_version_ids=(observation.content_version_id,),
                now=NOW,
            )
            assert len(frozen) == 1
            assert frozen[0].version_id == observation.content_version_id
            assert frozen[0].input_observation_ids == (observation.id,)
            assert frozen[0].author_name is None
            assert frozen[0].text_scope == "full"
            assert frozen[0].body == "Full controlled original source content"
            assert (
                load_editorial_source_names_in_transaction(
                    session, owner_id=uuid4(), source_keys=(profile.source_key,)
                )
                == {}
            )


def test_export_artifact_inherits_original_deadline_and_cleanup_without_breaking_replay(engine):
    from connections.editorial_services import capability_for
    from evidence.export_cleanup import attach_export_cleanup_targets_in_transaction
    from evidence.schemas import CleanupTargetSpec, DataClass
    from evidence.services import ResourceUnavailableError, SourceAccessPolicyService

    sessions = sessionmaker(engine, expire_on_commit=False)
    object_name = f"media/exports/{uuid4()}/artifact.json"
    with sessions() as session:
        service, owner, profile, _ = setup(session)
        _ingest(session, service, owner, profile)
        with session.begin():
            observation = session.scalar(select(ContentObservation))
            assert observation is not None
            expiry_before = session.scalar(
                text("SELECT expires_at FROM evidence_resources WHERE resource_id=:id"),
                {"id": observation.id},
            )
            attach_export_cleanup_targets_in_transaction(
                session,
                owner_id=owner,
                observation_ids=(observation.id,),
                object_name=object_name,
                now=NOW,
            )
            attach_export_cleanup_targets_in_transaction(
                session,
                owner_id=owner,
                observation_ids=(observation.id,),
                object_name=object_name,
                now=NOW,
            )
            admission = SourceAccessPolicyService(
                session, clock=lambda: NOW
            ).admit_payload_in_transaction(
                owner_id=owner,
                source_key=profile.source_key,
                capability=capability_for(profile.configuration.kind),
                data_class=DataClass.STRUCTURED,
                collected_at=observation.observed_at,
                payload={"body": "Full controlled original source content"},
            )
            original = LifecycleService(session, clock=lambda: NOW).track_resource_in_transaction(
                owner_id=owner,
                resource_type="content_observation",
                resource_id=observation.id,
                admission=admission,
                cleanup_targets=[
                    CleanupTargetSpec(
                        kind=CleanupTargetKind.POSTGRES_CONTENT_OBSERVATION,
                        reference=str(observation.id),
                    )
                ],
            )
            assert original.expires_at == expiry_before
            assert len(original.cleanup_targets) == 2
        deletion = LifecycleService(session, clock=lambda: NOW).request_deletion(
            owner_id=owner,
            operation_id=uuid4(),
            resource_type="content_observation",
            resource_id=observation.id,
            reason=DeletionReason.RETENTION_EXPIRED,
        )
        assert deletion.target_count == 2
        with session.begin(), pytest.raises(ResourceUnavailableError):
            attach_export_cleanup_targets_in_transaction(
                session,
                owner_id=owner,
                observation_ids=(observation.id,),
                object_name=object_name,
                now=NOW,
            )
    cleaned = []
    outcome = CleanupProcessor(
        sessions,
        handlers={
            CleanupTargetKind.POSTGRES_CONTENT_OBSERVATION: ContentObservationCleanup(
                sessions, clock=lambda: NOW
            ),
            CleanupTargetKind.MINIO_OBJECT: cleaned.append,
        },
        clock=lambda: NOW,
    ).process_due(limit=10)
    assert outcome.failed == 0 and outcome.succeeded == 2
    assert cleaned == [object_name]
