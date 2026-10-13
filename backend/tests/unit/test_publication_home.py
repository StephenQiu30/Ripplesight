"""Public home time classification is independent of source dates and material discovery."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from core.errors import DependencyUnavailableError
from events.fact_schemas import EventPublicationDevelopment, EventPublicationStoryView
from events.observation_inputs import load_fact_observation_inputs_in_transaction
from publication.reading import public_item
from publication.story_timing import public_story_timing
from tests.unit.test_publication_groups import member

NOW = datetime(2026, 10, 13, tzinfo=UTC)


def test_home_counts_all_events_across_100_identity_batches(monkeypatch):
    import publication.home as module
    from publication.schemas import PublicStoryTiming, PublicStoryView

    identities = [UUID(int=index + 1) for index in range(501)]
    sample = member(at=NOW).projection
    candidates = [
        SimpleNamespace(projection=sample.model_copy(update={"event_id": identity}))
        for identity in identities
    ]
    monkeypatch.setattr(
        module,
        "iter_current_publications_in_transaction",
        lambda *a, **kw: iter([*candidates, *candidates[:50]]),
    )
    batches = []

    def permitted(reader, *, event_ids, owner_id, now, strict_capacity, include_history):
        assert strict_capacity and now == NOW
        if not include_history:
            batches.append(event_ids)
        return [
            PublicStoryView(
                id=identity,
                revision=1,
                title="event",
                summary="permitted",
                latest_progress=None,
                phase="active",
                first_seen_at=NOW,
                reports=[
                    public_item(
                        sample.model_copy(update={"source_key": f"source-{identity.int % 3}"})
                    )
                ],
                timing=PublicStoryTiming(
                    snapshot_at=NOW,
                    reference_at=NOW,
                    reference_basis="published",
                    identified_at=NOW,
                    latest_development_at=None,
                    development_fact_ids=[],
                    activity="new",
                ),
            )
            for identity in event_ids
        ]

    monkeypatch.setattr(module, "public_stories_in_transaction", permitted)
    reader = SimpleNamespace(
        session=SimpleNamespace(in_transaction=lambda: True, get=lambda *_: None),
        indexing_enabled=False,
        public_categories=(),
    )
    view = module.home_in_transaction(reader, owner_id=uuid4(), now=NOW, limit=2)
    assert view.overview.total_events == view.overview.new_events_24h == 501
    assert view.overview.covered_sources == 3 and len(view.stories) == 2
    assert [len(batch) for batch in batches] == [100, 100, 100, 100, 100, 1]


def test_full_candidate_listing_crosses_500_keyset_boundary(monkeypatch):
    import publication.listing as module

    sample = member(at=NOW).projection.model_copy(update={"eligible": False})
    rows = [
        SimpleNamespace(content_id=UUID(int=index + 1), timeline_at=NOW) for index in range(501)
    ]
    calls = []

    def scalars(query):
        calls.append(query)
        return rows[:500] if len(calls) == 1 else rows[500:]

    class Reader:
        def __init__(self, *a, **kw):
            assert kw["strict_capacity"]

        def _live(self, *, rows, **kw):
            return {
                row.content_id: (
                    sample.model_copy(update={"content_id": row.content_id}),
                    SimpleNamespace(run=None),
                )
                for row in rows
            }

        def source_icon_url(self, key):
            return None

    monkeypatch.setattr(module, "PublicationReadingService", Reader)
    session = SimpleNamespace(in_transaction=lambda: True, scalars=scalars)
    values = list(
        module.iter_current_publications_in_transaction(
            session, owner_id=uuid4(), now=NOW, strict_capacity=True, recheck_all=True
        )
    )
    assert len(values) == 501 and len(calls) == 2
    assert rows[499].content_id in calls[1].compile().params.values()


@pytest.mark.parametrize(
    ("identified", "assigned", "activity"),
    [
        (NOW, None, "new"),
        (NOW - timedelta(hours=24) + timedelta(microseconds=1), None, "new"),
        (NOW - timedelta(hours=24), None, "existing"),
        (NOW - timedelta(days=2), NOW - timedelta(hours=24), "existing"),
        (NOW - timedelta(days=2), NOW, "existing_updated"),
        (NOW - timedelta(hours=1), NOW, "new"),
        (NOW + timedelta(microseconds=1), None, "unknown"),
        (NOW - timedelta(days=2), NOW + timedelta(microseconds=1), "unknown"),
        (NOW - timedelta(days=2), NOW - timedelta(days=3), "unknown"),
        (None, None, "unknown"),
    ],
)
def test_time_window_boundaries_and_unknowns(identified, assigned, activity):
    event, fact = uuid4(), uuid4()
    report = public_item(member(at=NOW, event=event, fact=fact).projection)
    story = EventPublicationStoryView(
        event_id=event,
        topic_id=uuid4(),
        revision=20,
        title="event",
        summary="summary",
        latest_progress="regenerated text",
        phase="active",
        first_seen_at=NOW - timedelta(days=100),
        first_seen_basis="published",
        created_at=identified,
        members=(),
        developments=(EventPublicationDevelopment(fact, assigned, (report.id,)),)
        if assigned
        else (),
    )
    timing = public_story_timing(story, reports=[report], now=NOW)
    assert timing.activity == activity
    assert timing.reference_basis == "published"
    assert timing.occurred_at is None
    assert timing.identified_at == identified
    # Material discovered now, a large revision and regenerated text do not imply a development.
    if assigned is None:
        assert timing.latest_development_at is None and timing.development_fact_ids == []


def test_development_requires_matching_public_fact_and_nonlegacy_report_identity():
    event, fact = uuid4(), uuid4()
    report = public_item(member(at=NOW, event=event, fact=fact).projection)
    story = EventPublicationStoryView(
        event_id=event,
        topic_id=uuid4(),
        revision=1,
        title="event",
        summary="summary",
        latest_progress=None,
        phase="active",
        first_seen_at=NOW - timedelta(days=10),
        created_at=NOW - timedelta(days=2),
        members=(),
        developments=(EventPublicationDevelopment(fact, NOW, (uuid4(),)),),
    )
    assert public_story_timing(story, reports=[report], now=NOW).activity == "existing"
    story = replace(story, developments=(EventPublicationDevelopment(fact, NOW, (report.id,)),))
    timing = public_story_timing(story, reports=[report], now=NOW)
    assert timing.activity == "existing_updated" and timing.development_fact_ids == [fact]
    other_fact = report.model_copy(update={"fact_id": uuid4()})
    assert public_story_timing(story, reports=[other_fact], now=NOW).activity == "existing"
    # A valid assignment must not conceal another invalid time for the same public evidence.
    story = replace(
        story,
        developments=(
            *story.developments,
            EventPublicationDevelopment(fact, NOW + timedelta(seconds=1), (report.id,)),
        ),
    )
    assert public_story_timing(story, reports=[report], now=NOW).activity == "unknown"


@pytest.mark.parametrize("count", [2000, 2001])
def test_mixed_fact_member_capacity_is_explicit_in_strict_reads(count):
    facts = (uuid4(), uuid4())
    rows = [(SimpleNamespace(fact_id=facts[index % 2]), None) for index in range(count)]
    session = SimpleNamespace(
        in_transaction=lambda: True, execute=lambda _: SimpleNamespace(all=lambda: rows)
    )
    # Both individual facts are below capacity; only the combined closed input exceeds it.
    if count == 2001:
        with pytest.raises(
            DependencyUnavailableError, match="publication_distribution_unavailable"
        ):
            load_fact_observation_inputs_in_transaction(
                session, owner_id=uuid4(), fact_ids=facts, now=NOW, strict_capacity=True
            )
    else:
        assert (
            load_fact_observation_inputs_in_transaction(
                session, owner_id=uuid4(), fact_ids=facts, now=NOW, strict_capacity=True
            )
            == {}
        )
    assert (
        load_fact_observation_inputs_in_transaction(
            session, owner_id=uuid4(), fact_ids=facts, now=NOW
        )
        == {}
    )
