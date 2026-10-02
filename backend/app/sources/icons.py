"""AIHOT source icon candidate rules (MIT), without requests or reading-time discovery."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from sources.editorial_schemas import public_url

BATCH = 200
RETRY_DAYS = 30
MP_RETRY_DAYS = 3
MP_PAUSE_SECONDS = 3
MAX_ICON_CANDIDATES = 5


def _public(value: str) -> str | None:
    try:
        return public_url(value)
    except ValueError:
        return None


def icon_candidates(html: str, base: str) -> tuple[str, ...]:
    if len(html.encode()) > 10_000_000:
        raise ValueError("icon page exceeds its bounded input")
    safe_base = _public(base)
    if safe_base is None:
        raise ValueError("icon page must have a public HTTP origin")
    found: list[tuple[str, int]] = []
    for tag in BeautifulSoup(html, "html.parser").find_all("link", limit=1000):
        rel = tag.get("rel")
        rel = (
            " ".join(str(item) for item in rel).casefold()
            if isinstance(rel, list)
            else str(rel).casefold()
        )
        href = tag.get("href")
        if "icon" not in rel or not isinstance(href, str) or not href or href.startswith("data:"):
            continue
        url = _public(urljoin(safe_base, href))
        if url is None:
            continue
        sizes = max(
            (int(m[1]) for m in re.finditer(r"(\d+)x\d+", str(tag.get("sizes", "")))), default=0
        )
        score = (1000 if "apple-touch-icon" in rel else 0) + min(sizes, 512)
        score += 200 if re.search(r"\.svg(?:\?|$)", href, re.IGNORECASE) else 0
        score -= 300 if re.search(r"\.ico(?:\?|$)", href, re.IGNORECASE) else 0
        found.append((url, score))
    ordered = [url for url, _ in sorted(found, key=lambda row: row[1], reverse=True)]
    ordered.append(urljoin(safe_base, "/favicon.ico"))
    return tuple(dict.fromkeys(ordered))


def home_of(article_urls: tuple[str, ...], configuration: Mapping[str, object]) -> str | None:
    origins = []
    for value in article_urls[:10]:
        safe = _public(value)
        if safe is not None:
            parts = urlsplit(safe)
            origins.append(f"{parts.scheme}://{parts.netloc}")
    if origins:
        top, count = Counter(origins).most_common(1)[0]
        if count >= max(1, len(origins) * 0.7):
            return top
    configured = (
        configuration.get("url") or configuration.get("feed_url") or configuration.get("feedUrl")
    )
    if not isinstance(configured, str):
        return None
    configured = re.sub(r"^https?://r\.jina\.ai/", "", configured)
    safe = _public(configured)
    if safe is None:
        return None
    parts = urlsplit(safe)
    return f"{parts.scheme}://{parts.netloc}"


def mp_avatar(html: str) -> str | None:
    if len(html.encode()) > 10_000_000:
        raise ValueError("MP icon page exceeds its bounded input")
    match = re.search(r"round_head_img\s*[:=]\s*[\"']([^\"']{1,2048})[\"']", html)
    return _public(re.sub(r"^http:", "https:", match[1])) if match else None
