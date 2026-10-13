"""Translate event-owned times using only evidence surviving public permission guards."""

from datetime import datetime, timedelta

from events.fact_schemas import EventPublicationStoryView
from publication.schemas import PublicItemView, PublicStoryTiming


def public_story_timing(
    story: EventPublicationStoryView, *, reports: list[PublicItemView], now: datetime
) -> PublicStoryTiming:
    """Classify system activity, without claiming when an event actually happened."""
    supported = {(report.fact_id, report.id) for report in reports}
    developments = [
        item
        for item in story.developments
        if any((item.fact_id, identity) in supported for identity in item.content_ids)
    ]
    identified = story.created_at
    invalid = (
        identified is None
        or identified.utcoffset() is None
        or identified > now
        or story.first_seen_at.utcoffset() is None
        or story.first_seen_at > now
    )
    if identified is not None:
        invalid = invalid or any(
            item.assigned_at.utcoffset() is None
            or item.assigned_at > now
            or item.assigned_at < identified
            for item in developments
        )
    latest = max((item.assigned_at for item in developments), default=None) if not invalid else None
    start = now - timedelta(hours=24)
    activity = (
        "unknown"
        if invalid or identified is None
        else "new"
        if identified > start
        else "existing_updated"
        if latest is not None and latest > start
        else "existing"
    )
    return PublicStoryTiming(
        snapshot_at=now,
        reference_at=story.first_seen_at,
        reference_basis=story.first_seen_basis,
        identified_at=identified,
        latest_development_at=latest,
        development_fact_ids=sorted({item.fact_id for item in developments}, key=str),
        activity=activity,
    )
