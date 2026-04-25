from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from xml.etree import ElementTree

import httpx

from apps.api.app.core.settings import settings
from apps.api.app.models.keyword import Keyword
from apps.api.app.models.source import Source

DEFAULT_RSS_URL = "https://hnrss.org/frontpage"
HN_BASE_URL = "https://hacker-news.firebaseio.com/v0"


@dataclass(slots=True)
class Candidate:
    title: str
    url: str
    source_id: int
    keyword_id: int | None
    author: str | None
    published_at: datetime | None
    snippet: str | None
    raw_payload: dict[str, Any]


class SourceIngestionError(RuntimeError):
    pass


def fetch_candidates(source: Source, keyword: Keyword) -> list[Candidate]:
    source_type = source.source_type.lower()
    if source_type == "rss":
        return _fetch_rss(source, keyword)
    if source_type in {"hacker_news", "hacker-news", "hn"}:
        return _fetch_hacker_news(source, keyword)
    raise SourceIngestionError(f"Unsupported source_type: {source.source_type}")


def _fetch_rss(source: Source, keyword: Keyword) -> list[Candidate]:
    url = str(source.config.get("url") or DEFAULT_RSS_URL)
    limit = int(source.config.get("limit") or settings.source_fetch_limit)
    try:
        response = httpx.get(url, timeout=15)
        response.raise_for_status()
        root = ElementTree.fromstring(response.text)
    except Exception as exc:  # noqa: BLE001
        raise SourceIngestionError(f"RSS fetch failed for {source.name}: {exc}") from exc

    items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
    candidates: list[Candidate] = []
    for item in items[:limit]:
        title = _xml_text(item, "title")
        link = _rss_link(item)
        snippet = _xml_text(item, "description") or _xml_text(item, "summary")
        author = _xml_text(item, "author") or _xml_text(item, "{http://purl.org/dc/elements/1.1/}creator")
        published = _parse_datetime(_xml_text(item, "pubDate") or _xml_text(item, "published") or _xml_text(item, "updated"))
        if not title or not link:
            continue
        candidates.append(
            Candidate(
                title=title,
                url=link,
                source_id=source.id,
                keyword_id=keyword.id,
                author=author,
                published_at=published,
                snippet=_strip_html(snippet),
                raw_payload={"source_type": "rss", "feed_url": url},
            )
        )
    return candidates


def _fetch_hacker_news(source: Source, keyword: Keyword) -> list[Candidate]:
    limit = int(source.config.get("limit") or settings.source_fetch_limit)
    endpoint = str(source.config.get("endpoint") or "topstories")
    try:
        with httpx.Client(timeout=15) as client:
            story_ids = client.get(f"{HN_BASE_URL}/{endpoint}.json").raise_for_status().json()
            candidates: list[Candidate] = []
            for story_id in story_ids[:limit]:
                item = client.get(f"{HN_BASE_URL}/item/{story_id}.json").raise_for_status().json()
                title = item.get("title")
                url = item.get("url") or f"https://news.ycombinator.com/item?id={story_id}"
                snippet = item.get("text")
                if not title or not url:
                    continue
                candidates.append(
                    Candidate(
                        title=title,
                        url=url,
                        source_id=source.id,
                        keyword_id=keyword.id,
                        author=item.get("by"),
                        published_at=datetime.fromtimestamp(item["time"], tz=timezone.utc) if item.get("time") else None,
                        snippet=_strip_html(snippet),
                        raw_payload={"source_type": "hacker_news", "id": story_id, "score": item.get("score")},
                    )
                )
            return candidates
    except Exception as exc:  # noqa: BLE001
        raise SourceIngestionError(f"Hacker News fetch failed for {source.name}: {exc}") from exc


def _xml_text(item: ElementTree.Element, tag: str) -> str | None:
    element = item.find(tag)
    if element is None or element.text is None:
        return None
    return element.text.strip()


def _rss_link(item: ElementTree.Element) -> str | None:
    link = _xml_text(item, "link")
    if link:
        return link
    atom_link = item.find("{http://www.w3.org/2005/Atom}link")
    if atom_link is not None:
        return atom_link.attrib.get("href")
    return None


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None


def _strip_html(value: str | None) -> str | None:
    if not value:
        return None
    return " ".join(value.replace("<p>", " ").replace("</p>", " ").replace("<br>", " ").split())
