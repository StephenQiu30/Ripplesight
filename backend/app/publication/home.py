"""Full-site public event overview from the same guarded snapshot as its bounded list."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from core.publication_config import PublicNegativeSurgePolicy
from publication.hotlists import public_platform_trends_in_transaction
from publication.listing import iter_current_publications_in_transaction
from publication.negative_surge import evaluate_negative_surge, negative_surge_summary
from publication.reading import PublicationReadingService
from publication.report_sentiment import merge_public_sentiment_samples, public_report_sentiment
from publication.schemas import (
    PublicHomeOverview,
    PublicHomeView,
    PublicNegativeSurgeEvent,
    PublicSentimentSample,
    PublicStoryView,
)
from publication.stories import public_stories_in_transaction


def _rank(story: PublicStoryView) -> tuple[bool, float, datetime, str]:
    eligible = bool(story.attention and story.attention.eligible and story.heat is not None)
    identified = story.timing.identified_at if story.timing else None
    return (
        eligible,
        story.heat or 0 if eligible else 0,
        story.attention.last_source_time
        if eligible and story.attention
        else identified or datetime.min.replace(tzinfo=UTC),
        str(story.id),
    )


def home_in_transaction(
    reader: PublicationReadingService,
    *,
    owner_id: UUID,
    now: datetime,
    limit: int = 50,
    surge_policy: PublicNegativeSurgePolicy | None = None,
) -> PublicHomeView:
    """Scan all current public candidates; fail rather than publish partial statistics.

    The caller owns a repeatable-read, read-only transaction. No publication,
    grouping, collection or model execution is triggered by this read.
    """
    if not reader.session.in_transaction() or now.utcoffset() is None:
        raise RuntimeError("public home requires an aware caller snapshot")
    if not 1 <= limit <= 50:
        raise ValueError("bounded public home list required")
    seen: set[UUID] = set()
    candidates: list[UUID] = []
    sources: set[str] = set()
    ranked: list[PublicStoryView] = []
    samples: dict[UUID, PublicSentimentSample] = {}
    decisions: list[PublicNegativeSurgeEvent] = []
    counts = {
        "total_events": 0,
        "new_events_24h": 0,
        "updated_events_24h": 0,
        "time_unknown_events": 0,
    }

    def consume() -> None:
        nonlocal ranked
        current = public_stories_in_transaction(
            reader,
            owner_id=owner_id,
            event_ids=tuple(candidates),
            now=now,
            strict_capacity=True,
            include_history=False,
        )
        for story in current:
            decisions.append(evaluate_negative_surge(story, now=now, policy=surge_policy))
            counts["total_events"] += 1
            if story.sentiment:
                merge_public_sentiment_samples(samples, story.sentiment.samples)
            sources.update(item.source.key for item in story.reports)
            activity = story.timing.activity if story.timing else "unknown"
            if activity == "new":
                counts["new_events_24h"] += 1
            elif activity == "existing_updated":
                counts["updated_events_24h"] += 1
            elif activity == "unknown":
                counts["time_unknown_events"] += 1
        ranked = sorted([*ranked, *current], key=_rank, reverse=True)[:limit]
        candidates.clear()

    for member in iter_current_publications_in_transaction(
        reader.session,
        owner_id=owner_id,
        now=now,
        indexing_enabled=reader.indexing_enabled,
        public_categories=reader.public_categories,
        strict_capacity=True,
        recheck_all=True,
    ):
        projection = member.projection
        if projection.selected and (
            projection.visible_after is None or projection.visible_after > now
        ):
            continue
        if projection.event_id is None or projection.event_id in seen:
            continue
        seen.add(projection.event_id)
        candidates.append(projection.event_id)
        if len(candidates) == 100:
            consume()
    if candidates:
        consume()
    if ranked:
        enriched = {
            story.id: story
            for story in public_stories_in_transaction(
                reader,
                owner_id=owner_id,
                event_ids=tuple(story.id for story in ranked),
                now=now,
                strict_capacity=True,
                include_history=True,
            )
        }
        ranked = [enriched[story.id] for story in ranked if story.id in enriched]
    surge = negative_surge_summary(decisions, now=now, policy=surge_policy)
    return PublicHomeView(
        snapshot_at=now,
        window_start=now - timedelta(hours=24),
        overview=PublicHomeOverview(
            **counts,
            covered_sources=len(sources),
            negative_surge_count=surge.triggered_count
            if surge_policy is not None and surge.evaluated_events == surge.total_events
            else None,
        ),
        stories=ranked,
        sentiment=public_report_sentiment(list(samples.values()), now=now, include_samples=False),
        negative_surge=surge,
        platform_trends=public_platform_trends_in_transaction(
            reader.session, owner_id=owner_id, now=now
        ),
    )
