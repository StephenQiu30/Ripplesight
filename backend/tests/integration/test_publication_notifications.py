from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import text
from tests.integration.test_editorial_execution import (
    NOW,
    ControlledClient,
    _budget,
    _execute,
    _run,
)
from tests.integration.test_publication import editorial_client as editorial_client

from publication.notification_reading import (
    list_selected_notification_candidates_in_transaction,
    load_selected_notification_candidate_in_transaction,
    weekly_selected_source_counts_in_transaction,
)
from publication.schemas import PublicationOverrideInput, SourcePolicyInput
from publication.services import PublicationService


def test_selected_notification_rechecks_fixed_revision_and_does_not_replay_history(
    editorial_client: TestClient,
) -> None:
    owner, run, message, lease = _run(editorial_client)
    _budget(editorial_client, owner)
    _execute(editorial_client, owner, message, lease, ControlledClient())
    sessions = editorial_client.app.state.session_factory
    with sessions.begin() as session:
        service = PublicationService(session)
        service.save_source_policy_in_transaction(
            owner_id=owner,
            actor_id=owner,
            source_key="x",
            command=SourcePolicyInput(
                operation_id=uuid4(),
                expected_revision=0,
                participation_mode="editorial",
                license_name="受控摘要许可",
                reason="通知固定样本",
            ),
            now=NOW,
        )
        publication = service.publish_in_transaction(
            owner_id=owner, content_id=run.content_id, now=NOW
        )
        assert publication
        revision = publication.revision
        assert not list_selected_notification_candidates_in_transaction(
            session, owner_id=owner, enabled_at=NOW, now=NOW
        ).candidates
    later = NOW + timedelta(seconds=181)
    with sessions.begin() as session:
        baseline = session.execute(text("SELECT count(*) FROM publication_revisions")).scalar_one()
        page = list_selected_notification_candidates_in_transaction(
            session, owner_id=owner, enabled_at=NOW, now=later
        )
        assert len(page.candidates) == 1 and page.next_after_content_id is None
        candidate = page.candidates[0]
        assert candidate.content_id == run.content_id
        assert candidate.publication_revision == revision
        assert candidate.selected_at == NOW
        assert candidate.dedupe_key == f"item:{run.content_id}"
        assert candidate.reading_url == f"/items/{run.content_id}"
        assert len(candidate.fingerprint) == 64
        assert candidate.title and candidate.summary
        weekly = weekly_selected_source_counts_in_transaction(session, owner_id=owner, now=later)
        assert [
            (entry.source_key, entry.current_count, entry.previous_count) for entry in weekly
        ] == [("x", 1, 0)]
        assert "body" not in candidate.model_dump()
        assert (
            load_selected_notification_candidate_in_transaction(
                session,
                owner_id=owner,
                content_id=run.content_id,
                publication_revision=revision,
                now=later,
            )
            == candidate
        )
        assert not list_selected_notification_candidates_in_transaction(
            session,
            owner_id=owner,
            enabled_at=NOW + timedelta(seconds=1),
            now=later,
        ).candidates
        assert not list_selected_notification_candidates_in_transaction(
            session, owner_id=uuid4(), enabled_at=NOW, now=later
        ).candidates
        assert (
            session.execute(text("SELECT count(*) FROM publication_revisions")).scalar_one()
            == baseline
        )
        assert session.execute(text("SELECT count(*) FROM ai_calls")).scalar_one() == 5
    with sessions.begin() as session:
        PublicationService(session).override_in_transaction(
            owner_id=owner,
            actor_id=owner,
            content_id=run.content_id,
            command=PublicationOverrideInput(
                operation_id=uuid4(),
                expected_revision=revision,
                visibility="summary-only",
                reason="发送前收紧许可",
            ),
            now=later,
        )
    with sessions.begin() as session:
        assert (
            load_selected_notification_candidate_in_transaction(
                session,
                owner_id=owner,
                content_id=run.content_id,
                publication_revision=revision,
                now=later,
            )
            is None
        )
        assert not list_selected_notification_candidates_in_transaction(
            session, owner_id=owner, enabled_at=NOW, now=later
        ).candidates
        weekly = weekly_selected_source_counts_in_transaction(session, owner_id=owner, now=later)
        assert [(entry.current_count, entry.previous_count) for entry in weekly] == [(1, 0)]
        assert not weekly_selected_source_counts_in_transaction(
            session, owner_id=uuid4(), now=later
        )
        PublicationService(session).override_in_transaction(
            owner_id=owner,
            actor_id=owner,
            content_id=run.content_id,
            command=PublicationOverrideInput(
                operation_id=uuid4(),
                expected_revision=revision + 1,
                visibility="withdrawn",
                reason="周度真实精选撤回",
            ),
            now=later,
        )
        assert not weekly_selected_source_counts_in_transaction(session, owner_id=owner, now=later)
