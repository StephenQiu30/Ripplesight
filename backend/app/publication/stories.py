"""Public stories require permission for every fixed narrative member."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select

from content.observation_context import load_observation_context_in_transaction
from events.reads import load_publication_stories_in_transaction
from publication.publication_models import PublicationRecord, PublicationSourcePolicy
from publication.reading import PublicationReadingService
from publication.schemas import PublicAttentionView, PublicStoriesPage, PublicStoryView


def public_stories_in_transaction(
    reader: PublicationReadingService, *, owner_id: UUID, event_ids: tuple[UUID, ...], now: datetime
) -> list[PublicStoryView]:
    stories = load_publication_stories_in_transaction(
        reader.session, owner_id=owner_id, event_ids=event_ids, now=now
    )
    references = {
        member.content_id: member.content_version_id
        for story in stories.values()
        for member in story.members
    }
    values = {}
    ids = tuple(references)
    for offset in range(0, len(ids), 500):
        rows = list(
            reader.session.scalars(
                select(PublicationRecord).where(
                    PublicationRecord.owner_id == owner_id,
                    PublicationRecord.content_id.in_(ids[offset : offset + 500]),
                )
            )
        )
        values.update(reader._live(owner_id=owner_id, rows=rows, now=now))
    result = []
    for story in stories.values():
        reports = []
        allowed = True
        indexable = reader.indexing_enabled
        if not story.narrative_input_observation_ids:
            continue
        # Private-readable historical reports can still forbid public use. The
        # narrative's complete inputs are independent of its active card subset.
        for observation_id in story.narrative_input_observation_ids:
            actual = load_observation_context_in_transaction(
                reader.session, owner_id=owner_id, observation_id=observation_id
            )
            policy = (
                reader.session.get(PublicationSourcePolicy, (owner_id, actual.source_key))
                if actual
                else None
            )
            if (
                actual is None
                or actual.published_at is None
                or policy is None
                or policy.configuration.get("participation_mode")
                not in {
                    "editorial",
                    "hot_signal",
                }
            ):
                allowed = False
                break
        if not allowed:
            continue
        for member in story.members:
            value = values.get(member.content_id)
            if value is None:
                allowed = False
                break
            projection = value[0]
            indexable = indexable and projection.indexable
            if (
                projection.content_version_id != member.content_version_id
                or projection.observation_id != member.observation_id
                or projection.source_key != member.source_key
                or projection.visibility != "public"
                or projection.published_at is None
                or (
                    projection.selected
                    and (projection.visible_after is None or projection.visible_after > now)
                )
            ):
                allowed = False
                break
            # The narrative can depend on a whole analysis batch beyond visible
            # reports. Its actual sources need current public participation too.
            for observation_id in member.input_observation_ids:
                actual = load_observation_context_in_transaction(
                    reader.session, owner_id=owner_id, observation_id=observation_id
                )
                policy = (
                    reader.session.get(PublicationSourcePolicy, (owner_id, actual.source_key))
                    if actual
                    else None
                )
                if (
                    actual is None
                    or actual.published_at is None
                    or policy is None
                    or policy.configuration.get("participation_mode")
                    not in {
                        "editorial",
                        "hot_signal",
                    }
                ):
                    allowed = False
                    break
            if not allowed:
                break
            if projection.event_id == story.event_id and projection.fact_id:
                reports.append(reader.item(projection))
        if allowed and reports:
            reports.sort(key=lambda item: (item.timeline_at, str(item.id)))
            attention = story.attention
            result.append(
                PublicStoryView(
                    id=story.event_id,
                    revision=story.revision,
                    title=story.title,
                    summary=story.summary,
                    latest_progress=story.latest_progress,
                    phase=story.phase,
                    first_seen_at=story.first_seen_at,
                    heat=story.heat,
                    attention=PublicAttentionView(
                        **attention.model_dump(
                            exclude={
                                "event_id",
                                "event_revision",
                                "source_names",
                                "roster",
                                "representative",
                                "interaction",
                            }
                        ),
                        last_source_time=max(
                            (item.source_time for item in attention.roster),
                            default=story.first_seen_at,
                        ),
                    )
                    if attention
                    else None,
                    reports=reports,
                    indexable=indexable,
                )
            )
    return result


def rank_public_hot_stories(stories: list[PublicStoryView]) -> list[PublicStoryView]:
    return sorted(
        [
            story
            for story in stories
            if story.attention and story.attention.eligible and story.heat is not None
        ],
        key=lambda story: (
            story.heat or 0,
            story.attention.last_source_time if story.attention else story.first_seen_at,
            str(story.id),
        ),
        reverse=True,
    )


def hot_stories_in_transaction(
    reader: PublicationReadingService, *, owner_id: UUID, now: datetime, limit: int = 10
) -> PublicStoriesPage:
    if not 1 <= limit <= 50:
        raise ValueError("bounded public stories required")
    query = select(PublicationRecord).where(
        PublicationRecord.owner_id == owner_id,
        PublicationRecord.visibility == "public",
        PublicationRecord.selected.is_(True),
        PublicationRecord.data["event_id"].astext.is_not(None),
    )
    after: UUID | None = None
    seen: set[UUID] = set()
    ids: list[UUID] = []
    ranked: list[PublicStoryView] = []
    while True:
        batch_query = query.where(PublicationRecord.content_id > after) if after else query
        rows = list(
            reader.session.scalars(batch_query.order_by(PublicationRecord.content_id).limit(500))
        )
        for row in rows:
            identity = UUID(row.data["event_id"])
            if identity in seen:
                continue
            seen.add(identity)
            ids.append(identity)
            if len(ids) == 100:
                current = public_stories_in_transaction(
                    reader, owner_id=owner_id, event_ids=tuple(ids), now=now
                )
                ranked = rank_public_hot_stories([*ranked, *current])[:limit]
                ids.clear()
        if len(rows) < 500:
            break
        after = rows[-1].content_id
    if ids:
        ranked = rank_public_hot_stories(
            [
                *ranked,
                *public_stories_in_transaction(
                    reader, owner_id=owner_id, event_ids=tuple(ids), now=now
                ),
            ]
        )[:limit]
    return PublicStoriesPage(stories=ranked, ranking_basis="heat")
