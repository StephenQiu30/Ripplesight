from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session
from tests.integration.test_editorial_source_profiles import NOW, begin, job, page, setup
from tests.integration.test_editorial_source_profiles import engine as engine

from analysis.editorial_reading import scan_current_editorial_publication_ids_in_transaction
from connections.editorial_models import EditorialSourceMaterialReceipt
from jobs.schemas import JobAcceptanceInput, JobObservationContext
from jobs.services import JobService
from publication.reading import PublicationReadingService
from publication.schemas import SourcePolicyInput
from publication.search import search_in_transaction
from publication.services import PublicationService
from sources.editorial_schemas import EditorialMaterial


def ingest(session, *, allow_body=True):
    service, owner, profile, command = setup(session)
    if not allow_body:
        with session.begin():
            session.execute(
                text(
                    "UPDATE source_access_policies SET field_purposes=field_purposes - 'body' "
                    "WHERE owner_id=:owner"
                ),
                {"owner": owner},
            )
    accepted, operation = job(session, owner, profile)
    prepared = begin(service, owner, profile, accepted, operation)
    materials = tuple(
        EditorialMaterial(
            identity_key=f"guid:{number}",
            external_id=str(number),
            url=f"https://example.com/{number}",
            title=f"Original title {number}",
            excerpt="Actual source abstract" if number == 1 else "",
            published_at=NOW - timedelta(hours=1) if number == 1 else None,
        )
        for number in (1, 2)
    )
    service.stage_page(owner_id=owner, run_id=prepared.result.run_id, page=page(*materials))
    assert service.apply_page(owner_id=owner, run_id=prepared.result.run_id).created == 2
    with session.begin():
        ids = tuple(session.scalars(select(EditorialSourceMaterialReceipt.content_id)))
        publisher = PublicationService(session)
        publisher.save_source_policy_in_transaction(
            owner_id=owner,
            actor_id=owner,
            source_key=profile.source_key,
            command=SourcePolicyInput(
                operation_id=uuid4(),
                expected_revision=0,
                participation_mode="editorial",
                license_name="Controlled metadata licence",
                reason="Original metadata reading without model execution",
                release_delay_seconds=0,
            ),
            now=NOW,
        )
        operation = uuid4()
        publication_job = JobService(session, clock=lambda: NOW).accept_in_transaction(
            owner_id=owner,
            command=JobAcceptanceInput(
                operation_id=operation,
                kind="publication.republish",
                observation=JobObservationContext(
                    configuration_ref=f"publication-source:{profile.source_key}",
                    configuration_version=1,
                ),
                scope={"source_key": profile.source_key},
            ),
        )
        run = publisher.create_republish_in_transaction(
            owner_id=owner,
            source_key=profile.source_key,
            job_id=publication_job.id,
            operation_id=operation,
            now=NOW,
        )
        result = publisher.republish_page_in_transaction(owner_id=owner, run_id=run, now=NOW)
        assert result["processed"] == 2
    return service, owner, profile, command, ids


def test_raw_metadata_republish_and_reads_do_not_fabricate_analysis_or_fulltext(engine):
    with Session(engine, expire_on_commit=False) as session:
        _, owner, profile, _, ids = ingest(session)
        with session.begin():
            assert scan_current_editorial_publication_ids_in_transaction(
                session, owner_id=owner, source_key=profile.source_key, limit=10
            ).content_ids == tuple(sorted(ids))
            before = session.scalar(text("SELECT count(*) FROM jobs"))
            reader = PublicationReadingService(session)
            result = reader.items_in_transaction(owner_id=owner, now=NOW)
            assert len(result.items) == 2
            assert result.source_status[0].health == "ok"
            assert result.source_status[0].last_success_at == NOW
            searched = search_in_transaction(reader, owner_id=owner, query="Original", now=NOW)
            assert len(searched.items) == 2 and searched.source_status == result.source_status
            by_title = {item.title: item for item in result.items}
            assert by_title["Original title 1"].summary == "Actual source abstract"
            assert by_title["Original title 1"].summary_origin == "source"
            absent = by_title["Original title 2"]
            assert absent.summary is None and absent.summary_origin == "none"
            assert absent.published_at is None and absent.discovered_at == NOW
            assert not reader.items_in_transaction(owner_id=owner, now=NOW, selected=True).items
            assert not reader.items_in_transaction(owner_id=uuid4(), now=NOW).items
            for item in result.items:
                assert item.analysis_state == "not_analyzed" and not item.selected
                assert item.score is None and item.category is None and item.event_id is None
                detail = reader.detail_in_transaction(owner_id=owner, content_id=item.id, now=NOW)
                assert detail and detail.body is None and not detail.site_fulltext
            assert session.scalar(text("SELECT count(*) FROM jobs")) == before
            for table in ("editorial_runs", "editorial_content_states", "ai_calls"):
                assert session.scalar(text(f"SELECT count(*) FROM {table}")) == 0


def test_source_pause_retains_public_metadata_but_live_revocation_removes_it(engine):
    with Session(engine, expire_on_commit=False) as session:
        service, owner, profile, command, ids = ingest(session)
        service.save_profile(
            owner_id=owner,
            profile_id=profile.id,
            command=command.model_copy(
                update=dict(operation_id=uuid4(), expected_revision=profile.revision, enabled=False)
            ),
        )
        with session.begin():
            reader = PublicationReadingService(session)
            result = reader.items_in_transaction(owner_id=owner, now=NOW)
            assert len(result.items) == 2 and not result.source_status[0].enabled
        with session.begin():
            session.execute(
                text("UPDATE source_access_policies SET enabled=false WHERE owner_id=:owner"),
                {"owner": owner},
            )
        with session.begin():
            reader = PublicationReadingService(session)
            assert not reader.items_in_transaction(owner_id=owner, now=NOW).items
            assert reader.detail_in_transaction(owner_id=owner, content_id=ids[0], now=NOW) is None


def test_metadata_only_permission_never_persists_or_publishes_unlicensed_abstract(engine):
    with Session(engine, expire_on_commit=False) as session:
        _, owner, _, _, _ = ingest(session, allow_body=False)
        with session.begin():
            result = PublicationReadingService(session).items_in_transaction(
                owner_id=owner, now=NOW
            )
            assert len(result.items) == 2
            assert all(
                item.summary is None and item.summary_origin == "none" for item in result.items
            )
            assert (
                session.scalar(text("SELECT count(*) FROM content_versions WHERE body IS NOT NULL"))
                == 0
            )
