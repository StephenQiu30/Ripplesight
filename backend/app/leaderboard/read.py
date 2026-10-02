"""Reader filtering is a view of a computed run; it never recalculates rankings."""

from collections.abc import Sequence

from leaderboard.method.types import BoardEntry


def filter_entries(
    entries: Sequence[BoardEntry],
    *,
    domestic: bool = False,
    open_weights: bool = False,
    domestic_slugs: frozenset[str] = frozenset(),
    weight_urls: dict[str, str] | None = None,
    limit: int = 30,
) -> tuple[BoardEntry, ...]:
    if limit < 1 or limit > 500:
        raise ValueError("Leaderboard view limit must be between 1 and 500")
    return tuple(
        entry
        for entry in entries
        if (not domestic or entry.slug in domestic_slugs)
        and (not open_weights or bool((weight_urls or {}).get(entry.slug)))
    )[:limit]
