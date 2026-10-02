"""Pure preview parser and metadata projection using the real collector rules."""

from collections.abc import Sequence
from datetime import datetime
from time import monotonic

from sources.adapters.editorial_json import parse_json_list
from sources.adapters.editorial_rss import parse_feed
from sources.adapters.editorial_web import parse_web_list
from sources.editorial_preview_schemas import (
    EditorialPreviewItem,
    EditorialSamplePreviewInput,
    EditorialSourcePreviewView,
)
from sources.editorial_registry import filter_materials
from sources.editorial_schemas import EditorialCursor, EditorialMaterial


def preview_items(rows: Sequence[EditorialMaterial]) -> tuple[EditorialPreviewItem, ...]:
    return tuple(
        EditorialPreviewItem(
            title=row.title,
            url=row.url,
            published_at=row.published_at,
            excerpt=(row.excerpt or row.body_text or "")[:200],
        )
        for row in rows[:20]
    )


def preview_sample(
    command: EditorialSamplePreviewInput, *, now: datetime
) -> EditorialSourcePreviewView:
    started = monotonic()
    config = command.configuration
    rows = (
        parse_feed(command.sample, config.feed_url or "", config)
        if config.kind == "rss"
        else parse_json_list(command.sample, config)
        if config.kind == "json_list"
        else parse_web_list(command.sample, config.url or "", config)
    )
    rows = filter_materials(rows, config, EditorialCursor(initialized_at=now), now)
    return EditorialSourcePreviewView(
        mode="sample",
        status="complete",
        kind=config.kind,
        count=len(rows),
        ms=int((monotonic() - started) * 1000),
        requests=0,
        items=preview_items(rows),
    )
