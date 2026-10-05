"""RSS/Atom/RDF semantic port of AIHOT sources/rss.ts; MIT attribution at repository root."""

import contextlib
import re
from datetime import datetime
from typing import Any
from urllib.parse import urljoin, urlsplit

import feedparser
from bs4 import BeautifulSoup

from sources.adapters.editorial_http import EditorialSourceError
from sources.adapters.editorial_parsing import (
    EditorialParsingStats,
    collapse,
    material,
    parse_loose_date,
    plain,
    required_terms_match,
    sanitize_html,
    summary_excerpt,
)
from sources.editorial_identity import rsshub_native_identity_proofs
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
    text: str | bytes,
    response_url: str,
    config: EditorialSourceConfiguration,
    *,
    stats: EditorialParsingStats | None = None,
) -> tuple[EditorialMaterial, ...]:
    if config.kind != "rss":
        raise ValueError("RSS parser requires RSS configuration")
    rsshub = config.rsshub
    encoded = text.encode() if isinstance(text, str) else text
    if rsshub and (encoded.lstrip().lower().startswith((b"<html", b"<!doctype html"))):
        login = any(
            word in encoded.lower()
            for word in (b"login", b"log in", b"captcha", "验证码".encode(), "登录".encode())
        )
        raise EditorialSourceError(
            "rsshub_authentication_required" if login else "rsshub_html_response", blocked=login
        )
    if b"<!ENTITY" in (text.encode() if isinstance(text, str) else text).upper():
        raise ValueError("feed entity declarations are unsupported")
    doc = feedparser.parse(
        text,
        response_headers={"content-location": response_url, "content-type": "application/xml"},
    )
    if not doc.version or (doc.bozo and not doc.entries):
        raise ValueError("not a supported RSS/Atom feed")
    if rsshub and doc.bozo:
        raise ValueError("malformed local RSSHub feed cannot establish a complete snapshot")
    if rsshub and not doc.entries:
        raise EditorialSourceError("rsshub_empty_snapshot_unverified")
    if rsshub and len(doc.entries) > rsshub.max_items:
        raise EditorialSourceError("rsshub_item_bound_exceeded")
    out = []
    stats = stats if stats is not None else EditorialParsingStats()
    filtered_before = stats.filtered
    native_proofs = rsshub_native_identity_proofs(
        text,
        configuration=config,
        parsed_links=tuple(
            entry.get("link") if isinstance(entry.get("link"), str) else None
            for entry in doc.entries[:1000]
        ),
    )
    for index, entry in enumerate(doc.entries[:1000]):
        url = entry.get("link")
        title = entry.get("title")
        if not isinstance(url, str) or not isinstance(title, str) or not title.strip():
            if rsshub:
                raise ValueError("local RSSHub entries require a stable public link and title")
            continue
        if rsshub and urlsplit(url).hostname not in rsshub.item_hosts:
            raise EditorialSourceError("rsshub_item_target_unapproved", blocked=True)
        contents = entry.get("content", [])
        body = (
            contents[0].get("value", "")
            if contents
            else entry.get("summary", "")
            if config.summary_is_body
            else ""
        )
        summary = entry.get("summary", "")
        atom = doc.version.startswith("atom")
        body_is_text = atom and (
            contents[0].get("type") == "text/plain"
            if contents
            else entry.get("summary_detail", {}).get("type") == "text/plain"
        )
        summary_is_text = atom and entry.get("summary_detail", {}).get("type") == "text/plain"
        if body_is_text:
            if len(body) > 100_000:
                raise ValueError("source body exceeds its limit")
            html, body_text = None, body.strip() or None
        else:
            html, body_text = sanitize_html(body, url) if body else (None, None)
        teaser = bool(body_text and is_teaser(body_text))
        source_summary = (
            (summary.strip() if summary_is_text else sanitize_html(summary, url)[1])
            if summary
            else body_text
            if body_text
            else None
        )
        complete = bool(
            body_text and (config.summary_is_body or len(body_text) > 280) and not teaser
        )
        if rsshub:
            # RSS route descriptions are an observed text scope, not a proven
            # article, transcript or platform-native ID. Keep the original URL.
            source_summary = collapse(plain(summary or body)) or None
            complete = False
        title_is_text = atom and entry.get("title_detail", {}).get("type") == "text/plain"
        excerpt, truncated = summary_excerpt(
            source_summary, config.summary_max_chars, default_limit=4000
        )
        media = []
        enclosures = entry.get("enclosures", [])
        for enclosure in enclosures:
            if str(enclosure.get("type", "")).startswith("image/") and enclosure.get("href"):
                with contextlib.suppress(ValueError):
                    media.append(public_url(urljoin(url, enclosure["href"])))
        for image in BeautifulSoup("" if body_is_text else body, "html.parser").find_all(
            "img", src=True
        ):
            with contextlib.suppress(ValueError):
                media.append(public_url(urljoin(url, str(image["src"]))))

        def date(name: str, current: Any = entry) -> datetime | None:
            # Feedparser assumes UTC for naive Atom dates and aliases missing updated
            # to published. Use actual raw keys and the frozen source offset instead.
            raw: Any = current.get(name) if name in current else None
            return (
                parse_loose_date(raw, config.published_at_utc_offset)
                if isinstance(raw, str)
                else None
            )

        try:
            candidate = material(
                url,
                title,
                title_is_text=title_is_text,
                preserve_fragment=config.preserve_url_fragment,
                external_id=None if rsshub else str(entry.get("id", ""))[:512] or None,
                native_identity=native_proofs[index],
                author=entry.get("author", None),
                published_at=date("published") if rsshub else date("published") or date("updated"),
                source_updated_at=date("updated"),
                excerpt=excerpt,
                body_html=html if complete else None,
                body_text=body_text if complete else None,
                body_status="ok" if complete else "pending",
                media=tuple(dict.fromkeys(media))[:6],
                categories=tuple(
                    str(tag.get("term", "")) for tag in entry.get("tags", []) if tag.get("term")
                )[:100],
                metadata={
                    **({"summary_truncated": True} if truncated else {}),
                    **(
                        {
                            "collector": "rsshub",
                            "collector_revision": rsshub.revision,
                            "query_mode": rsshub.query_mode,
                            "returned_text_scope": rsshub.text_scope,
                            "snapshot_scope": "limited_feed",
                            "identity_basis": "canonical_url",
                            "feed_guid": str(entry.get("id", ""))[:512] or None,
                            "downstream_request_count": None,
                        }
                        if rsshub
                        else {}
                    ),
                },
            )
        except ValueError:
            if rsshub:
                raise
            continue
        if not required_terms_match(candidate.title, source_summary, config.require_any_terms):
            stats.filtered += 1
            continue
        out.append(candidate)
    if doc.entries and not out and stats.filtered == filtered_before:
        raise ValueError("feed entries did not map to valid materials")
    return tuple(out)
