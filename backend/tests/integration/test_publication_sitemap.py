from __future__ import annotations

from datetime import timedelta
from uuid import uuid4
from xml.etree import ElementTree

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from tests.integration.test_editorial_execution import NOW
from tests.integration.test_publication import _manual_posts
from tests.integration.test_publication import editorial_client as editorial_client

from core.errors import ApplicationError
from publication.application import PublicationApplicationService
from publication.schemas import PublicationOverrideInput, SourcePolicyInput
from publication.services import PublicationService


def test_sitemap_is_bounded_shards_with_live_permission_checks_and_default_empty_index(
    editorial_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import publication.application as application

    monkeypatch.setattr(application, "SITEMAP_SHARD_SIZE", 2)
    owner, posts = _manual_posts(editorial_client, 3)
    sessions = editorial_client.app.state.session_factory
    with sessions.begin() as session:
        PublicationService(session, indexing_enabled=True).save_source_policy_in_transaction(
            owner_id=owner,
            actor_id=owner,
            source_key="x",
            command=SourcePolicyInput(
                operation_id=uuid4(),
                expected_revision=1,
                participation_mode="editorial",
                site_fulltext=True,
                indexable=True,
                license_name="受控可索引许可",
                reason="分片验收",
            ),
            now=NOW,
        )
        for post in posts:
            PublicationService(session, indexing_enabled=True).publish_in_transaction(
                owner_id=owner,
                content_id=post.id,
                now=NOW,
                released_at=NOW - timedelta(minutes=1),
            )
    later = NOW + timedelta(seconds=181)
    with sessions() as session:
        app = PublicationApplicationService(
            session, origin="https://hotkey.example", indexing_enabled=True
        )
        index = ElementTree.fromstring(app.sitemap(owner_id=owner, now=later))
        locs = [node.text for node in index.findall("{*}sitemap/{*}loc")]
        assert locs == [
            "https://hotkey.example/sitemaps/items-0.xml",
            "https://hotkey.example/sitemaps/items-1.xml",
        ]
        first = ElementTree.fromstring(app.sitemap_shard(owner_id=owner, shard=0, now=later))
        second = ElementTree.fromstring(app.sitemap_shard(owner_id=owner, shard=1, now=later))
        all_locs = [node.text for tree in (first, second) for node in tree.findall("{*}url/{*}loc")]
        assert len(first) == 2 and len(second) == 1
        assert set(all_locs) == {f"https://hotkey.example/items/{post.id}" for post in posts}
        hidden = PublicationApplicationService(session, indexing_enabled=False)
        assert len(ElementTree.fromstring(hidden.sitemap(owner_id=owner, now=later))) == 0
        assert (
            len(ElementTree.fromstring(hidden.sitemap_shard(owner_id=owner, shard=0, now=later)))
            == 0
        )
        with pytest.raises(ApplicationError, match="resource_not_found"):
            app.sitemap_shard(owner_id=owner, shard=2, now=later)
        with pytest.raises(ApplicationError, match="invalid_publication_input"):
            app.sitemap_shard(owner_id=owner, shard=1_000_000, now=later)
    with sessions.begin() as session:
        PublicationService(session, indexing_enabled=True).override_in_transaction(
            owner_id=owner,
            actor_id=owner,
            content_id=posts[0].id,
            command=PublicationOverrideInput(
                operation_id=uuid4(),
                expected_revision=1,
                visibility="summary-only",
                reason="撤销可索引完整文章",
            ),
            now=later,
        )
    with sessions() as session:
        app = PublicationApplicationService(session, indexing_enabled=True)
        xml = app.sitemap_shard(owner_id=owner, shard=0, now=later) + app.sitemap_shard(
            owner_id=owner, shard=1, now=later
        )
        assert str(posts[0].id) not in xml
        assert session.execute(text("SELECT count(*) FROM ai_calls")).scalar_one() == 0
        assert session.execute(text("SELECT count(*) FROM publication_revisions")).scalar_one() == 4
