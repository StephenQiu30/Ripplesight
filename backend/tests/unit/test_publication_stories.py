from datetime import UTC, datetime, timedelta
from uuid import uuid4

from publication.schemas import PublicAttentionView, PublicStoryView
from publication.stories import rank_public_hot_stories


def test_heat_ranking_uses_latest_source_tie_and_omits_unknown_or_ineligible_attention() -> None:
    now = datetime(2026, 10, 2, tzinfo=UTC)

    def story(heat: float, last: datetime, *, eligible: bool = True) -> PublicStoryView:
        return PublicStoryView(
            id=uuid4(),
            revision=1,
            title="事实",
            summary="已许可摘要",
            latest_progress=None,
            phase="active",
            first_seen_at=now - timedelta(days=10),
            heat=heat,
            reports=[],
            attention=PublicAttentionView(
                formula_version="source-uniform-48h-v1",
                window_end=now,
                last_source_time=last,
                heat=heat,
                eligible=eligible,
                participant_count=2,
                editorial_participant_count=1,
                signal_participant_count=1,
                comparable_participant_count=0,
                uncomparable_participant_count=2,
                comparable_heat=0,
                comparable_previous_heat=0,
                previous_heat=0,
                trend="unknown",
                trend_pct=None,
                complete=True,
                badges=[],
            ),
        )

    old, recent = story(1, now - timedelta(hours=1)), story(1, now)
    hottest = story(2, now - timedelta(days=1))
    missing = recent.model_copy(update={"id": uuid4(), "attention": None, "heat": None})
    ineligible = story(10, now, eligible=False)
    assert rank_public_hot_stories([old, recent, missing, hottest, ineligible]) == [
        hottest,
        recent,
        old,
    ]


def test_item_related_story_list_fills_after_unreadable_candidates_and_uses_public_all_member_gate(
    monkeypatch,
) -> None:
    from uuid import UUID

    from publication.reading import PublicationReadingService

    now = datetime(2026, 10, 2, tzinfo=UTC)
    identities = [UUID(int=value) for value in range(1, 110)]
    support = {identity: 200 - index for index, identity in enumerate(identities)}
    owner, current = uuid4(), uuid4()
    calls = []
    monkeypatch.setattr(
        "events.consolidation.load_related_story_ids_in_transaction",
        lambda session, **kwargs: support,
    )

    def permitted(reader, **kwargs):
        assert kwargs["owner_id"] == owner and kwargs["now"] == now
        assert len(kwargs["event_ids"]) <= 100
        calls.extend(kwargs["event_ids"])
        return [
            PublicStoryView(
                id=identity,
                revision=3,
                title="当前许可事件",
                summary="全部固定成员已获许可",
                latest_progress=None,
                phase="active",
                first_seen_at=now,
                heat=None,
                attention=None,
                reports=[],
            )
            for identity in kwargs["event_ids"]
            if identity in identities[100:]
        ]

    monkeypatch.setattr("publication.stories.public_stories_in_transaction", permitted)
    result = PublicationReadingService(None)._related_stories_in_transaction(
        owner_id=owner, event_id=current, now=now
    )
    assert [row.id for row in result] == identities[100:106]
    assert [row.supporting_reports for row in result] == [
        support[identity] for identity in identities[100:106]
    ]
    assert all(
        row.revision == 3 and row.reading_url == f"/discover/stories/{row.id}" for row in result
    )
    assert calls == identities
