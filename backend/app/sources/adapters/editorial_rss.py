"""RSS/Atom/RDF semantic port of AIHOT sources/rss.ts; MIT attribution at repository root."""

import calendar
import contextlib
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin

import feedparser
from bs4 import BeautifulSoup

from sources.adapters.editorial_parsing import collapse, material, plain, sanitize_html
from sources.editorial_schemas import EditorialMaterial, EditorialSourceConfiguration, public_url

_TEASER = re.compile(
    (
        "\\bappeared first on\\b|\\bread (?:the )?full (?:story|article)\\b|\\b"
        "continue reading\\b|\\bread more\\b|…\\s*$|\\[\\s*(?:…|\\.\\.\\.)\\s*\\]\\s*$"
    ),
    re.IGNORECASE,
)


def is_teaser(text: str) -> bool:
    return len(text.strip()) < 1200 and bool(_TEASER.search(text.strip()))


def parse_feed(
    text: str | bytes, response_url: str, config: EditorialSourceConfiguration
) -> tuple[EditorialMaterial, ...]:
    if config.kind != "rss":
        raise ValueError("RSS parser requires RSS configuration")
    if b"<!ENTITY" in (text.encode() if isinstance(text, str) else text).upper():
        raise ValueError("feed entity declarations are unsupported")
    doc = feedparser.parse(
        text,
        response_headers={"content-location": response_url, "content-type": "application/xml"},
    )
    if not doc.version or (doc.bozo and not doc.entries):
        raise ValueError("not a supported RSS/Atom feed")
    out = []
    for entry in doc.entries[:1000]:
        url = entry.get("link")
        title = entry.get("title")
        if not isinstance(url, str) or not isinstance(title, str) or not title.strip():
            continue
        contents = entry.get("content", [])
        body = (
            contents[0].get("value", "")
            if contents
            else entry.get("summary", "")
            if config.summary_is_body
            else ""
        )
        summary = entry.get("summary", "")
        html, body_text = sanitize_html(body, url) if body else (None, None)
        teaser = bool(body_text and is_teaser(body_text))
        excerpt = (
            collapse(plain(summary))[:2000]
            if summary
            else collapse(body_text)[:2000]
            if teaser and body_text
            else None
        )
        complete = bool(body_text and len(body_text) > 280 and not teaser)
        media = []
        enclosures = entry.get("enclosures", [])
        for enclosure in enclosures:
            if str(enclosure.get("type", "")).startswith("image/") and enclosure.get("href"):
                with contextlib.suppress(ValueError):
                    media.append(public_url(urljoin(url, enclosure["href"])))
        for image in BeautifulSoup(body, "html.parser").find_all("img", src=True):
            with contextlib.suppress(ValueError):
                media.append(public_url(urljoin(url, str(image["src"]))))

        def date(name: str, current: Any = entry) -> datetime | None:
            parsed: Any = current.get(f"{name}_parsed")
            return datetime.fromtimestamp(calendar.timegm(parsed), UTC) if parsed else None

        try:
            out.append(
                material(
                    url,
                    title,
                    preserve_fragment=config.preserve_url_fragment,
                    external_id=str(entry.get("id", ""))[:512] or None,
                    author=entry.get("author", None),
                    published_at=date("published") or date("updated"),
                    source_updated_at=date("updated"),
                    excerpt=excerpt,
                    body_html=html if complete else None,
                    body_text=body_text if complete else None,
                    body_status="ok" if complete else "pending",
                    media=tuple(dict.fromkeys(media))[:6],
                    categories=tuple(
                        str(tag.get("term", "")) for tag in entry.get("tags", []) if tag.get("term")
                    )[:100],
                )
            )
        except ValueError:
            continue
    if doc.entries and not out:
        raise ValueError("feed entries did not map to valid materials")
    return tuple(out)
