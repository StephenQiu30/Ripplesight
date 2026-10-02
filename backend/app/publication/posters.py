"""Deterministic local SVG posters; no model, external font, image or network."""

from __future__ import annotations

import html
from textwrap import wrap

from publication.exports import public_origin
from publication.schemas import PublicEditionView, PublicItemDetailView, PublicStoryView


def _lines(value: str, width: int, limit: int) -> list[str]:
    parts = []
    for paragraph in value.splitlines():
        parts.extend(wrap(paragraph, width=width, break_long_words=True, break_on_hyphens=False))
    if len(parts) > limit:
        parts = parts[:limit]
        parts[-1] = parts[-1].rstrip() + "…"
    return parts


def _text(y: int, text: str, size: int, color: str, weight: int = 400) -> str:
    return (
        f'<text x="106" y="{y}" font-family="sans-serif" font-size="{size}" '
        f'font-weight="{weight}" fill="{color}">{html.escape(text)}</text>'
    )


def _poster(*, title: str, summary: str, source: str, url: str, badge: str) -> str:
    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1440" '
        'viewBox="0 0 1080 1440">',
        f"<title>{html.escape(title)}</title>",
        '<rect width="1080" height="1440" fill="#101f2c"/>',
        '<rect x="56" y="56" width="968" height="1328" rx="28" fill="#f6f4eb"/>',
        _text(154, "HotKey", 32, "#2264a8"),
        _text(214, badge, 24, "#526579"),
    ]
    y = 320
    for line in _lines(title, 20, 4):
        lines.append(_text(y, line, 42, "#101f2c", 700))
        y += 62
    y += 70
    for line in _lines(summary, 28, 11):
        lines.append(_text(y, line, 29, "#344a5e"))
        y += 48
    for index, line in enumerate(_lines(source, 35, 2)):
        lines.append(_text(1190 + 48 * index, line, 22, "#526579"))
    for index, line in enumerate(_lines(url, 85, 2)):
        lines.append(_text(1300 + 28 * index, line, 17, "#526579"))
    lines.append("</svg>")
    return "\n".join(lines)


def item_poster(item: PublicItemDetailView, *, origin: str) -> str | None:
    if not item.markdown_available or not item.summary:
        return None
    return _poster(
        title=item.title,
        summary=item.summary,
        source=f"来源: {item.source.name}",
        url=public_origin(origin) + item.reading_url,
        badge="精选阅读 · 摘要节选",
    )


def story_poster(story: PublicStoryView, *, origin: str) -> str:
    names = list(dict.fromkeys(item.source.name for item in story.reports))
    return _poster(
        title=story.title,
        summary=story.summary,
        source="来源: " + " · ".join(names),
        url=public_origin(origin) + f"/discover/stories/{story.id}",
        badge="热点事件 · 固定证据复验",
    )


def edition_poster(edition: PublicEditionView, *, origin: str) -> str:
    return _poster(
        title=edition.title,
        summary=edition.lead,
        source=f"{edition.kind} {edition.key} · {len(edition.entries)}条精选",
        url=public_origin(origin) + f"/reports/{edition.kind}/{edition.key}",
        badge="日周月刊 · 摘要节选",
    )
