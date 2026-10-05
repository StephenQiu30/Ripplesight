"""Strict JSON API/embedded data port of AIHOT sources/json-list.ts; no eval."""

import json
import math
from datetime import UTC, datetime
from typing import Any

from sources.adapters.editorial_parsing import (
    embedded_json,
    get_path,
    material,
    parse_loose_date,
    plain,
    render_template,
)
from sources.editorial_schemas import EditorialMaterial, EditorialSourceConfiguration


def parse_json_list(
    text: str, config: EditorialSourceConfiguration
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
            continue
        if config.min_numeric:
            try:
                value = float(get_path(item, config.min_numeric.path))
                if not math.isfinite(value) or value < config.min_numeric.min:
                    continue
            except (ValueError, TypeError):
                continue
        title = first(item, config.title_paths)
        url = render_template(config.url_template, item) if config.url_template else None
        if not url and config.url_template_fallback:
            url = render_template(config.url_template_fallback, item)
        if not title or not url:
            continue
        summary = first(item, config.summary_paths)
        external: Any = get_path(item, config.external_id_path) if config.external_id_path else None
        date_value = get_path(item, config.published_at_path) if config.published_at_path else None
        published_at = date(date_value)
        metadata = (
            {"publication_date_reason": "invalid_publication_date"}
            if published_at is None and date_value not in (None, "")
            else {}
        )
        try:
            out.append(
                material(
                    url,
                    title,
                    author=first(item, config.author_paths),
                    external_id=str(external)[:512] if external is not None else None,
                    published_at=published_at,
                    metadata=metadata,
                    excerpt=plain(summary)[:2000] if summary else None,
                    body_text=plain(summary) if config.summary_is_body and summary else None,
                    body_status="ok" if config.summary_is_body and summary else "pending",
                )
            )
        except ValueError:
            continue
    if items and not out and not (config.require_boolean or config.min_numeric):
        raise ValueError("JSON items did not map to title/URL materials")
    return tuple(out)
