from datetime import timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import text
from tests.integration.test_content_records import _command
from tests.integration.test_editorial_execution import NOW
from tests.integration.test_publication import _manual_posts
from tests.integration.test_publication import editorial_client as editorial_client

from analysis.editorial_schemas import EditorialOverrideInput, EditorialRunInput
from analysis.editorial_services import EditorialService
from content.services import ContentService
from publication.application import PublicationApplicationService
from publication.schemas import PublicationOverrideInput, SourcePolicyInput
from publication.services import PublicationService


def _quoted_post(client: TestClient):
    owner, targets = _manual_posts(client, 1)
    sessions = client.app.state.session_factory
    with sessions() as session:
        context = session.execute(
            text(
                "SELECT c.id AS connection,p.id AS policy,r.id AS retention,j.id AS job "
                "FROM source_connections c JOIN source_access_policies p ON p.owner_id=c.owner_id "
                "AND p.source_key=c.source_key JOIN evidence_retention_policies r "
                "ON r.source_policy_id=p.id JOIN jobs j ON j.owner_id=c.owner_id "
                "AND j.source_key=c.source_key WHERE c.owner_id=:owner LIMIT 1"
            ),
            {"owner": owner},
        ).one()
        subject = ContentService(session).persist_post(
            owner_id=owner,
            command=_command(
                owner_id=owner,
                connection_id=context.connection,
                policy_id=context.policy,
                retention_id=context.retention,
                job_id=context.job,
                operation_id=uuid4(),
                observed_at=NOW - timedelta(minutes=1),
                external_id="quote-subject",
                extra_fields={
                    "text_scope": "full",
                    "text_origin": "source",
                    "title": "引用报道",
                    "body": "引用报道自己的正文",
                    "published_at": None,
                    "quote_target_external_id": "search-0",
                },
            ),
        )
    with sessions() as session:
        service = EditorialService(session, clock=lambda: NOW)
        run = service.request_run(
            owner_id=owner,
            content_id=subject.id,
            source_key="x",
            command=EditorialRunInput(
                operation_id=uuid4(),
                content_version_id=subject.latest_observation.content_version.id,
            ),
        )
        service.override(
            owner_id=owner,
            run_id=run.id,
            command=EditorialOverrideInput(
                operation_id=uuid4(),
                expected_manual_version=0,
                selected=True,
                title_zh="引用报道标题",
                summary_zh="引用报道摘要",
                reason="受控引用阅读",
            ),
        )
    with sessions.begin() as session:
        for post in (targets[0], subject):
            PublicationService(session).publish_in_transaction(
                owner_id=owner, content_id=post.id, now=NOW, released_at=NOW - timedelta(minutes=1)
            )
    return owner, targets[0], subject


def test_quote_card_requires_its_own_current_publication_and_separate_fulltext_grant(
    editorial_client: TestClient,
):
    owner, target, subject = _quoted_post(editorial_client)
    sessions = editorial_client.app.state.session_factory
    later = NOW + timedelta(seconds=181)
    assert editorial_client.get(f"/api/publication/items/{subject.id}/site").status_code == 200
    with sessions() as session:
        service = PublicationApplicationService(session)
        detail = service.detail(owner_id=owner, content_id=subject.id, now=later)
        assert detail.quoted_post and detail.quoted_post.item.id == target.id
        assert detail.quoted_post.body and "原始正文" in detail.quoted_post.body.original
        assert detail.quoted_post.author == "author-1"
        external = service.detail(
            owner_id=owner, content_id=subject.id, now=later, redistribute=True
        )
        assert external.body is None and external.quoted_post and external.quoted_post.body is None
        assert session.scalar(text("SELECT count(*) FROM ai_calls")) == 0
    with sessions.begin() as session:
        PublicationService(session).override_in_transaction(
            owner_id=owner,
            actor_id=owner,
            content_id=target.id,
            command=PublicationOverrideInput(
                operation_id=uuid4(),
                expected_revision=1,
                visibility="summary-only",
                reason="引用目标只有摘要许可",
            ),
            now=later,
        )
    with sessions() as session:
        detail = PublicationApplicationService(session).detail(
            owner_id=owner, content_id=subject.id, now=later
        )
        assert detail.body and detail.quoted_post and detail.quoted_post.body is None
        assert "原始正文" not in detail.quoted_post.model_dump_json()
    with sessions.begin() as session:
        PublicationService(session).override_in_transaction(
            owner_id=owner,
            actor_id=owner,
            content_id=target.id,
            command=PublicationOverrideInput(
                operation_id=uuid4(),
                expected_revision=2,
                visibility="withdrawn",
                reason="引用目标撤回",
            ),
            now=later,
        )
    with sessions() as session:
        detail = PublicationApplicationService(session).detail(
            owner_id=owner, content_id=subject.id, now=later
        )
        assert detail.body and detail.quoted_post is None
        assert str(target.id) not in detail.model_dump_json()
        assert session.scalar(text("SELECT count(*) FROM ai_calls")) == 0
    with sessions.begin() as session:
        PublicationService(session).save_source_policy_in_transaction(
            owner_id=owner,
            actor_id=owner,
            source_key="x",
            now=later,
            command=SourcePolicyInput(
                operation_id=uuid4(),
                expected_revision=1,
                participation_mode="isolated",
                license_name="许可撤回",
                reason="引用来源许可撤回",
            ),
        )
    response = editorial_client.get(f"/api/publication/items/{subject.id}/site")
    assert response.status_code == 404
    assert "原始正文" not in response.text and "引用报道自己的正文" not in response.text
