from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import publication.stories as module
from publication.reading import PublicationReadingService
from tests.unit.test_publication_groups import member


def test_story_index_requires_every_fixed_member_even_outside_report_subset(monkeypatch):
    now = datetime(2026, 10, 2, tzinfo=UTC)
    event_id, fact_id = uuid4(), uuid4()
    displayed = member(at=now, event=event_id, fact=fact_id).projection.model_copy(
        update={"indexable": True, "observation_id": uuid4()}
    )
    undisplayed = member(at=now).projection.model_copy(
        update={"indexable": False, "observation_id": uuid4()}
    )
    story = SimpleNamespace(
        event_id=event_id,
        revision=1,
        title="当前固定故事",
        summary="经许可复验的故事",
        latest_progress=None,
        phase="active",
        first_seen_at=now,
        heat=None,
        attention=None,
        narrative_input_observation_ids=(displayed.observation_id, undisplayed.observation_id),
        members=tuple(
            SimpleNamespace(
                content_id=p.content_id,
                content_version_id=p.content_version_id,
                observation_id=p.observation_id,
                source_key=p.source_key,
                input_observation_ids=(p.observation_id,),
            )
            for p in (displayed, undisplayed)
        ),
    )
    monkeypatch.setattr(
        module, "load_publication_stories_in_transaction", lambda *a, **k: {event_id: story}
    )
    source_by_observation = {p.observation_id: p.source_key for p in (displayed, undisplayed)}
    monkeypatch.setattr(
        module,
        "load_observation_context_in_transaction",
        lambda *a, observation_id, **k: SimpleNamespace(
            source_key=source_by_observation[observation_id]
        ),
    )
    reader = PublicationReadingService(
        SimpleNamespace(
            scalars=lambda _: [],
            get=lambda *a: SimpleNamespace(configuration={"participation_mode": "editorial"}),
        ),
        indexing_enabled=True,
    )
    values = {p.content_id: (p, None) for p in (displayed, undisplayed)}
    monkeypatch.setattr(reader, "_live", lambda **_: values)
    result = module.public_stories_in_transaction(
        reader, owner_id=uuid4(), event_ids=(event_id,), now=now
    )
    assert len(result) == 1 and len(result[0].reports) == 1
    assert not result[0].indexable
    values[undisplayed.content_id] = (undisplayed.model_copy(update={"indexable": True}), None)
    assert module.public_stories_in_transaction(
        reader, owner_id=uuid4(), event_ids=(event_id,), now=now
    )[0].indexable
    reader.indexing_enabled = False
    assert not module.public_stories_in_transaction(
        reader, owner_id=uuid4(), event_ids=(event_id,), now=now
    )[0].indexable


def test_hot_ranking_considers_story_after_two_thousand_raw_records(monkeypatch):
    from uuid import UUID

    from publication.schemas import PublicAttentionView, PublicStoryView

    now = datetime(2026, 10, 2, tzinfo=UTC)
    rows = [
        SimpleNamespace(content_id=UUID(int=i + 1), data={"event_id": str(UUID(int=i + 1))})
        for i in range(2001)
    ]
    offset = 0

    def scalars(_):
        nonlocal offset
        result = rows[offset : offset + 500]
        offset += 500
        return result

    def stories(reader, *, owner_id, event_ids, now):
        return [
            PublicStoryView(
                id=event,
                revision=1,
                title="当前故事",
                summary="许可摘要",
                latest_progress=None,
                phase="active",
                first_seen_at=now,
                reports=[],
                heat=float(event.int),
                attention=PublicAttentionView(
                    formula_version="fixed",
                    window_end=now,
                    last_source_time=now,
                    heat=float(event.int),
                    eligible=True,
                    participant_count=2,
                    editorial_participant_count=1,
                    signal_participant_count=1,
                    comparable_participant_count=2,
                    uncomparable_participant_count=0,
                    comparable_heat=1,
                    comparable_previous_heat=1,
                    previous_heat=1,
                    trend="flat",
                    trend_pct=0,
                    complete=True,
                    badges=[],
                ),
            )
            for event in event_ids
        ]

    monkeypatch.setattr(module, "public_stories_in_transaction", stories)
    reader = PublicationReadingService(SimpleNamespace(scalars=scalars))
    page = module.hot_stories_in_transaction(reader, owner_id=uuid4(), now=now, limit=10)
    assert page.stories[0].id == UUID(int=2001)
    assert len(page.stories) == 10 and page.ranking_basis == "heat"
