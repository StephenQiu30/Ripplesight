"""Deduplicate permission-checked report samples into material-discovery windows."""

from datetime import datetime, timedelta
from uuid import UUID

from publication.schemas import (
    PublicReportSentimentView,
    PublicSentimentSample,
    PublicSentimentWindow,
)


def merge_public_sentiment_samples(
    target: dict[UUID, PublicSentimentSample], samples: list[PublicSentimentSample]
) -> None:
    """Merge global identities; contradictory conclusions or metadata stay excluded."""
    for sample in samples:
        previous = target.get(sample.content_id)
        if previous is None:
            target[sample.content_id] = sample
        elif previous != sample:
            target[sample.content_id] = previous.model_copy(
                update={
                    "state": "conflict",
                    "label": None,
                    "discovered_at": previous.discovered_at
                    if previous.discovered_at == sample.discovered_at
                    else None,
                    "source_key": previous.source_key
                    if previous.source_key == sample.source_key
                    else "",
                    # Conflicts take precedence over a disputed backfill flag.
                    "backfill": previous.backfill
                    if previous.backfill == sample.backfill
                    else False,
                }
            )


def public_report_sentiment(
    samples: list[PublicSentimentSample], *, now: datetime, include_samples: bool = True
) -> PublicReportSentimentView:
    """Build exact adjacent windows, keeping unknown times and exclusions explicit."""
    unique: dict[UUID, PublicSentimentSample] = {}
    merge_public_sentiment_samples(unique, samples)
    valid_time = [
        sample
        for sample in unique.values()
        if sample.discovered_at is not None
        and sample.discovered_at.utcoffset() is not None
        and sample.discovered_at <= now
    ]

    def window(start: datetime, end: datetime) -> PublicSentimentWindow:
        members = [
            s for s in valid_time if s.discovered_at is not None and start < s.discovered_at <= end
        ]
        labels = {"positive": 0, "neutral": 0, "negative": 0}
        excluded: dict[str, int] = {}
        for sample in members:
            if sample.backfill:
                reason = "backfill"
            elif sample.backfill is None:
                reason = "unavailable"
            elif sample.state == "valid" and sample.label is not None:
                labels[sample.label] += 1
                continue
            else:
                reason = sample.state if sample.state != "valid" else "invalid"
            excluded[reason] = excluded.get(reason, 0) + 1
        valid = sum(labels.values())
        return PublicSentimentWindow(
            start=start,
            end=end,
            sample_count=len(members),
            valid_count=valid,
            **labels,
            excluded_counts=excluded,
            source_keys=sorted({s.source_key for s in members if s.source_key}),
            negative_ratio=labels["negative"] / valid if valid else None,
            analysis_coverage=valid / len(members) if members else None,
        )

    boundary = now - timedelta(hours=24)
    return PublicReportSentimentView(
        snapshot_at=now,
        current=window(boundary, now),
        previous=window(now - timedelta(hours=48), boundary),
        time_unknown_count=len(unique) - len(valid_time),
        samples=list(unique.values()) if include_samples else [],
    )
