from datetime import UTC, datetime, timedelta
from uuid import uuid4

from publication.group_schemas import PublicReadingFilters
from publication.listing import PublicationListingMember
from publication.reading_groups import build_timeline_cards, pick_representative
from publication.schemas import ProjectionView


def member(*, at: datetime, event=None, fact=None, first_party=False, full=False, score=50):
    return PublicationListingMember(
        ProjectionView(
            content_id=uuid4(),
            content_version_id=uuid4(),
            editorial_run_id=uuid4(),
            manual_version=0,
            source_profile_revision=1,
            policy_revision=1,
            publication_revision=1,
            event_id=event,
            event_revision=1 if event else None,
            fact_id=fact,
            root_fact_id=None,
            fact_revision=1 if fact else None,
            topic_id=None,
            source_key=str(uuid4()),
            source_name="公开来源",
            source_kind="rss",
            first_party=first_party,
            visibility="public",
            eligible=True,
            selected=True,
            title="已许可的事实",
            original_title=None,
            summary="已许可摘要",
            reason=None,
            category="ai-models",
            tags=[],
            score=score,
            channel="news",
            url="https://example.com/article",
            published_at=None,
            discovered_at=at,
            timeline_at=at,
            sort_at=at,
            backfill=False,
            selected_ready_at=at,
            visible_after=at,
            body_mode="full" if full else "summary",
            syndicate=False,
            indexable=False,
            input_fingerprint="a" * 64,
        ),
        (),
    )


def test_reading_representative_prefers_first_party_then_full_score_and_earliest() -> None:
    at = datetime(2026, 10, 2, tzinfo=UTC)
    high = member(at=at, score=99, full=True)
    first = member(at=at + timedelta(minutes=1), first_party=True, score=10)
    full = member(at=at + timedelta(minutes=2), first_party=True, full=True, score=5)
    earlier = member(at=at, first_party=True, full=True, score=5)
    assert pick_representative([high, first, full, earlier]) == earlier


def test_new_development_moves_story_anchor_but_representative_swap_does_not() -> None:
    now = datetime(2026, 10, 2, tzinfo=UTC)
    event, initiating, progress = uuid4(), uuid4(), uuid4()
    root = member(at=now - timedelta(hours=3), event=event, fact=initiating)
    sibling = member(at=now - timedelta(hours=2), event=event, fact=initiating, first_party=True)
    development = member(at=now - timedelta(hours=1), event=event, fact=progress)
    cards = build_timeline_cards(
        (root, sibling, development), filters=PublicReadingFilters(), now=now
    )
    assert len(cards) == 1 and cards[0].item.id == sibling.projection.content_id
    assert cards[0].anchor_at == development.projection.sort_at
    assert cards[0].group.development_count == 2 and cards[0].group.report_count == 3
    assert cards[0].group.additional_source_count == 1
    without_progress = build_timeline_cards(
        (root, sibling), filters=PublicReadingFilters(), now=now
    )
    assert without_progress[0].anchor_at == root.projection.sort_at


def test_complete_archive_stream_does_not_drop_reports_after_twenty_thousand() -> None:
    from uuid import UUID

    from publication.topics import topic_summaries

    now = datetime(2026, 10, 2, tzinfo=UTC)
    event, fact = uuid4(), uuid4()
    sample = member(at=now - timedelta(hours=1), event=event, fact=fact)

    def stream():
        for index in range(20_001):
            yield PublicationListingMember(
                sample.projection.model_copy(
                    update={"content_id": UUID(int=index + 1), "source_key": f"source-{index % 2}"}
                ),
                ("entity:openai",),
            )

    cards = build_timeline_cards(stream(), filters=PublicReadingFilters(), now=now)
    assert len(cards) == 1 and cards[0].group.report_count == 20_001
    assert cards[0].group.additional_source_count == 1
    directory = topic_summaries(stream(), now=now)
    assert next(topic for topic in directory.topics if topic.slug == "openai").total == 20_001
