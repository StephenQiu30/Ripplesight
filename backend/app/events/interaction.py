from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta

from events.heat_schemas import EventInteractionView

_METRIC_WEIGHTS = {"like_count": 1.0, "comment_count": 2.0, "repost_count": 3.0, "view_count": 0.01}


def compute_interaction(metrics: Mapping[str, Mapping[str, int | None]]) -> EventInteractionView:
    components: dict[str, float | None] = {}
    masks = {}
    for identity, values in metrics.items():
        masks[identity] = [key for key in _METRIC_WEIGHTS if values.get(key) is None]
        known = [values.get(key) for key in _METRIC_WEIGHTS]
        if all(value is None for value in known):
            components[identity] = None
        else:
            weighted = sum(
                (values.get(key) or 0) * weight for key, weight in _METRIC_WEIGHTS.items()
            )
            components[identity] = math.log1p(weighted)
    known_components = [value for value in components.values() if value is not None]
    score = sum(known_components) + math.log1p(len(metrics)) if known_components else None
    return EventInteractionView(
        score=score, post_count=len(metrics), components=components, unknown_masks=masks
    )


def compare_interaction_growth(
    current: EventInteractionView,
    history: Sequence[tuple[datetime, float]],
    *,
    at: datetime,
) -> EventInteractionView:
    if current.score is None:
        return current
    ordered = sorted(history, key=lambda row: row[0], reverse=True)
    points = []
    identities = set()
    for index in range(1, 10):
        target = at - timedelta(hours=3 * index)
        point = next(
            (row for row in ordered if target - timedelta(hours=1) <= row[0] <= target), None
        )
        if point is None or point[0] in identities:
            return current
        points.append(point[1])
        identities.add(point[0])
    increment = current.score - points[0]
    baseline = sum(points[index] - points[index + 1] for index in range(8)) / 8
    if baseline <= 0:
        return current
    return current.model_copy(
        update={
            "rising_state": "rising" if increment > 0 and increment >= 3 * baseline else "steady",
            "current_increment": increment,
            "baseline_increment": baseline,
        }
    )
