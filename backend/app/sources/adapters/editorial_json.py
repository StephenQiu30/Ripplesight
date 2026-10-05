"""Strict JSON API/embedded data port of AIHOT sources/json-list.ts; no eval."""

import json
import math
from datetime import UTC, datetime
from typing import Any

from pydantic import JsonValue

from sources.adapters.editorial_parsing import (
    EditorialParsingStats,
    embedded_json,
    get_path,
    material,
    parse_loose_date,
    plain,
    render_template,
    required_terms_match,
    summary_excerpt,
)
from sources.editorial_schemas import EditorialMaterial, EditorialSourceConfiguration


def parse_json_list(
    text: str, config: EditorialSourceConfiguration, *, stats: EditorialParsingStats | None = None
) -> tuple[EditorialMaterial, ...]:
    if config.kind != "json_list":
        raise ValueError("JSON parser requires JSON configuration")
    data = (
        embedded_json(text, window_var=config.window_var)
        if config.mode == "html_window_var"
        else embedded_json(text, key=config.json_key)
        if config.mode == "html_json_key"
        else json.loads(text)
    )
    items = get_path(data, config.items_path or config.json_key or "")
    if config.items_object_values and isinstance(items, dict):
        items = list(items.values())
    if not isinstance(items, list) or len(items) > 1000:
        raise ValueError("items path must resolve to a bounded array")
    out = []
    stats = stats if stats is not None else EditorialParsingStats()
    filtered_before = stats.filtered

    def first(item: object, paths: tuple[str, ...]) -> str | None:
        for path in paths:
            value = get_path(item, path)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, (float, int)) and not isinstance(value, bool):
                return str(value)
        return None

    def date(value: object) -> datetime | None:
        if not isinstance(value, (str, int, float)) or isinstance(value, bool) or value == "":
            return None
        try:
            if config.published_at_unit in {"epoch_ms", "epoch_s"}:
                return datetime.fromtimestamp(
                    float(str(value)) / (1000 if config.published_at_unit == "epoch_ms" else 1), UTC
                )
            if config.published_at_unit == "yyyymmdd":
                return datetime.strptime(str(value), "%Y%m%d").replace(tzinfo=UTC)
            return parse_loose_date(str(value), config.published_at_utc_offset)
        except (ValueError, OverflowError, OSError):
            return None

    for item in items:
        if (
            config.require_boolean
            and get_path(item, config.require_boolean.path) is not config.require_boolean.equals
        ):
            stats.filtered += 1
            continue
        if config.min_numeric:
            try:
                value = float(get_path(item, config.min_numeric.path))
                if not math.isfinite(value) or value < config.min_numeric.min:
                    stats.filtered += 1
                    continue
            except (ValueError, TypeError):
                stats.filtered += 1
                continue
        title = first(item, config.title_paths)
        url = render_template(config.url_template, item) if config.url_template else None
        if not url and config.url_template_fallback:
            url = render_template(config.url_template_fallback, item)
        if not title or not url:
            continue
        summary = first(item, config.summary_paths)
        try:
            summary_text = plain(summary) if summary else None
        except ValueError:
            continue
        excerpt, truncated = summary_excerpt(
            summary_text, config.summary_max_chars, default_limit=2000
        )
        external: Any = get_path(item, config.external_id_path) if config.external_id_path else None
        date_value = get_path(item, config.published_at_path) if config.published_at_path else None
        published_at = date(date_value)
        metadata: dict[str, JsonValue] = (
            {"publication_date_reason": "invalid_publication_date"}
            if published_at is None and date_value not in (None, "")
            else {}
        )
        if truncated:
            metadata["summary_truncated"] = True
        try:
            candidate = material(
                url,
                title,
                author=first(item, config.author_paths),
                external_id=str(external)[:512] if external is not None else None,
                published_at=published_at,
                metadata=metadata,
                excerpt=excerpt,
                body_text=summary_text if config.summary_is_body and summary else None,
                body_status="ok" if config.summary_is_body and summary else "pending",
            )
        except ValueError:
            continue
        if not required_terms_match(candidate.title, summary_text, config.require_any_terms):
            stats.filtered += 1
            continue
        out.append(candidate)
    if (
        items
        and not out
        and stats.filtered == filtered_before
        and not (config.require_boolean or config.min_numeric)
    ):
        raise ValueError("JSON items did not map to title/URL materials")
    return tuple(out)
