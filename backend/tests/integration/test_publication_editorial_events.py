"""An automatically formed story reconciles through the existing publication Job."""

from datetime import timedelta
from uuid import uuid4

from sqlalchemy import text
from tests.integration.test_editorial_events import (
    ClusterClient,
    EditorialWithFact,
    _candidate,
    _cluster_message,
)
from tests.integration.test_editorial_execution import _budget, _execute, _run
from tests.integration.test_publication import NOW
from tests.integration.test_publication import editorial_client as editorial_client
from tests.integration.test_publication_media_mirror import message_for

from events.services import EventClusterExecutor
from jobs.schemas import JobStatus
from monitors.editorial_events import editorial_event_topic_id
from publication.execution import PublicationRepublishExecutor
from publication.reading import PublicationReadingService
from publication.schedule import enqueue_due_publication_in_transaction
from publication.schemas import SourcePolicyInput
from publication.services import PublicationService


def test_automatic_editorial_story_updates_publication_and_sync_without_operator_republish(
    editorial_client, monkeypatch
):
    owner, run, message, lease = _run(editorial_client)
    _budget(editorial_client, owner)
    _execute(editorial_client, owner, message, lease, EditorialWithFact())
    sessions = editorial_client.app.state.session_factory
    with sessions.begin() as session:
        service = PublicationService(session)
        service.save_source_policy_in_transaction(
            owner_id=owner,
            actor_id=owner,
            source_key="x",
            now=NOW,
            command=SourcePolicyInput(
                operation_id=uuid4(),
                expected_revision=0,
                participation_mode="editorial",
                release_delay_seconds=0,
                license_name="controlled fixture",
                reason="automatic reconciliation test",
            ),
        )
        first = service.publish_in_transaction(owner_id=owner, content_id=run.content_id, now=NOW)
        assert first and first.revision == 1
        stored = session.execute(text("SELECT projection FROM publication_records")).scalar_one()
        assert stored["event_id"] is None

    cluster_at = NOW + timedelta(seconds=10)
    count, candidate = _candidate(sessions, owner, at=cluster_at)
    assert count == 1 and candidate.topic_id == editorial_event_topic_id(owner)
    provider = ClusterClient(run.content_version_id)
    monkeypatch.setattr("events.services.create_ai_client", lambda _: provider)
    cluster_message, cluster_lease = _cluster_message(sessions, candidate)
    settings = editorial_client.app.state.settings.model_copy(
        update={"events_cluster_enabled": True, "ai_enabled": True}
    )
    EventClusterExecutor(sessions, settings, clock=lambda: cluster_at).execute(
        cluster_message, cluster_lease
    )
    assert len(provider.calls) == 1
    with sessions.begin() as session:
        reader = PublicationReadingService(session)
        detail = reader.detail_in_transaction(
            owner_id=owner, content_id=run.content_id, now=cluster_at
        )
        assert detail and detail.event_id and detail.fact_id
        event_id = detail.event_id
        # A GET exposes the current grouping, but never mutates the synchronization ledger.
        stored = session.execute(
            text("SELECT revision,projection AS data FROM publication_records")
        ).one()
        assert stored.revision == 1 and stored.data["event_id"] is None
        calls = session.execute(text("SELECT count(*) FROM ai_calls")).scalar_one()
        assert calls == 6

    reconcile_at = NOW + timedelta(minutes=5)
    with sessions.begin() as session:
        assert enqueue_due_publication_in_transaction(session, now=reconcile_at) == 1
        assert enqueue_due_publication_in_transaction(session, now=reconcile_at) == 0
        job_id = session.execute(text("SELECT job_id FROM publication_republish_runs")).scalar_one()
        assert (
            session.execute(
                text("SELECT count(*) FROM outbox_messages WHERE aggregate_id=:job"),
                {"job": job_id},
            ).scalar_one()
            == 1
        )
    message, lease = message_for(sessions, job_id, reconcile_at)
    executor = PublicationRepublishExecutor(sessions, clock=lambda: reconcile_at)
    result = executor.execute(message, lease)
    assert result and result.status == JobStatus.SUCCEEDED
    executor.execute(message, lease)
    with sessions.begin() as session:
        stored = session.execute(
            text("SELECT revision,projection AS data FROM publication_records")
        ).one()
        assert stored.revision == 2 and stored.data["event_id"] == str(event_id)
        assert session.execute(text("SELECT count(*) FROM publication_revisions")).scalar_one() == 2
        reader = PublicationReadingService(session)
        epoch, sequence = reader.effective_sequence_in_transaction(owner_id=owner, now=reconcile_at)
        changes = reader.selected_changes_in_transaction(
            owner_id=owner, epoch=epoch, since=0, now=reconcile_at
        )
        assert sequence == 2 and len(changes.changes) == 2
        assert changes.changes[-1].item and changes.changes[-1].item.event_id == event_id
        assert session.execute(text("SELECT count(*) FROM ai_calls")).scalar_one() == calls
        assert enqueue_due_publication_in_transaction(session, now=reconcile_at) == 0
