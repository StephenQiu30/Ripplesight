from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select, text
from tests.integration.test_editorial_execution import ControlledClient, _budget, _execute, _run
from tests.integration.test_publication import NOW
from tests.integration.test_publication import editorial_client as editorial_client

from analysis.editorial_models import EditorialOverride
from content.models import ContentObservation
from content.services import ContentObservationCleanup
from evidence.schemas import CleanupTargetKind, DeletionReason
from evidence.services import CleanupProcessor, LifecycleService
from publication.schemas import SourcePolicyInput
from publication.services import PublicationService


def test_cleanup_withdraws_and_purges_published_projection_before_version_delete(editorial_client):
    owner, run, message, lease = _run(editorial_client)
    _budget(editorial_client, owner)
    _execute(editorial_client, owner, message, lease, ControlledClient())
    sessions = editorial_client.app.state.session_factory
    with sessions.begin() as session:
        publisher = PublicationService(session)
        publisher.save_source_policy_in_transaction(
            owner_id=owner,
            actor_id=owner,
            source_key="x",
            now=NOW,
            command=SourcePolicyInput(
                operation_id=uuid4(),
                expected_revision=0,
                participation_mode="editorial",
                release_delay_seconds=0,
                license_name="controlled cleanup fixture",
                reason="Physical cleanup contract",
            ),
        )
        assert publisher.publish_in_transaction(owner_id=owner, content_id=run.content_id, now=NOW)
        observation = session.scalar(
            select(ContentObservation).where(
                ContentObservation.content_version_id == run.content_version_id
            )
        )
        epoch = session.scalar(
            text("SELECT epoch FROM publication_sync_states WHERE owner_id=:owner"),
            {"owner": owner},
        )
        assert observation is not None
        session.add(
            EditorialOverride(
                id=uuid4(),
                owner_id=owner,
                run_id=run.id,
                operation_id=uuid4(),
                input_fingerprint=b"o" * 32,
                revision=1,
                before={"summary": "controlled old derived text"},
                after={"summary": "controlled new derived text"},
                reason="controlled cleanup override child",
                created_at=NOW,
            )
        )
    with sessions() as session:
        LifecycleService(session, clock=lambda: NOW).request_deletion(
            owner_id=owner,
            operation_id=uuid4(),
            resource_type="content_observation",
            resource_id=observation.id,
            reason=DeletionReason.USER_REQUEST,
        )
    result = CleanupProcessor(
        sessions,
        handlers={
            CleanupTargetKind.POSTGRES_CONTENT_OBSERVATION: ContentObservationCleanup(
                sessions, clock=lambda: NOW + timedelta(seconds=1)
            )
        },
        clock=lambda: NOW + timedelta(seconds=1),
    ).process_due(limit=10)
    assert result.failed == 0 and result.succeeded == 1
    with sessions.begin() as session:
        for table in (
            "content_versions",
            "publication_records",
            "publication_revisions",
            "publication_selected_changes",
            "editorial_runs",
            "editorial_overrides",
        ):
            assert (
                session.scalar(
                    text(f"SELECT count(*) FROM {table} WHERE owner_id=:owner"), {"owner": owner}
                )
                == 0
            )
        assert epoch != session.scalar(
            text("SELECT epoch FROM publication_sync_states WHERE owner_id=:owner"),
            {"owner": owner},
        )


def test_quote_deletion_purges_derived_story_and_preserves_independent_main_raw_material(
    editorial_client,
):
    from tests.integration.test_event_reading_boundaries import _other_content

    from analysis.editorial_models import EditorialRun
    from analysis.editorial_services import EditorialService, _fingerprint

    owner, run, message, lease = _run(editorial_client)
    quoted = _other_content(editorial_client, owner)
    quoted_version = quoted.latest_observation.content_version
    sessions = editorial_client.app.state.session_factory
    with sessions.begin() as session:
        original = session.get(EditorialRun, run.id)
        original.input_manifest = {
            "quote": {"content_id": str(quoted.id), "content_version_id": str(quoted_version.id)}
        }
        original.input_fingerprint = _fingerprint(
            EditorialService(session, clock=lambda: NOW)
            ._load_material(original)
            .model_dump(mode="json")
        )
    _budget(editorial_client, owner)
    _execute(editorial_client, owner, message, lease, ControlledClient())
    with sessions.begin() as session:
        publisher = PublicationService(session)
        publisher.save_source_policy_in_transaction(
            owner_id=owner,
            actor_id=owner,
            source_key="x",
            now=NOW,
            command=SourcePolicyInput(
                operation_id=uuid4(),
                expected_revision=0,
                participation_mode="editorial",
                release_delay_seconds=0,
                license_name="controlled quote cleanup",
                reason="Controlled quoted input cleanup",
            ),
        )
        assert publisher.publish_in_transaction(owner_id=owner, content_id=run.content_id, now=NOW)
        observation = session.scalar(
            select(ContentObservation).where(
                ContentObservation.content_version_id == quoted_version.id
            )
        )
    with sessions() as session:
        LifecycleService(session, clock=lambda: NOW).request_deletion(
            owner_id=owner,
            operation_id=uuid4(),
            resource_type="content_observation",
            resource_id=observation.id,
            reason=DeletionReason.USER_REQUEST,
        )
    result = CleanupProcessor(
        sessions,
        handlers={
            CleanupTargetKind.POSTGRES_CONTENT_OBSERVATION: ContentObservationCleanup(
                sessions, clock=lambda: NOW + timedelta(seconds=1)
            )
        },
        clock=lambda: NOW + timedelta(seconds=1),
    ).process_due(limit=10)
    assert result.failed == 0 and result.succeeded == 1
    with sessions.begin() as session:
        for table in (
            "editorial_runs",
            "editorial_stages",
            "editorial_content_states",
            "publication_records",
            "publication_revisions",
        ):
            assert (
                session.scalar(
                    text(f"SELECT count(*) FROM {table} WHERE owner_id=:owner"), {"owner": owner}
                )
                == 0
            )
        assert (
            session.scalar(
                text("SELECT count(*) FROM content_versions WHERE id=:id"),
                {"id": run.content_version_id},
            )
            == 1
        )
        assert (
            session.scalar(
                text("SELECT count(*) FROM content_versions WHERE id=:id"),
                {"id": quoted_version.id},
            )
            == 0
        )
