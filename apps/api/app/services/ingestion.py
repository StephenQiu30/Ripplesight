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
X_SEARCH_URL = "https://api.x.com/2/tweets/search/recent"
BING_SEARCH_URL = "https://api.bing.microsoft.com/v7.0/search"
BILIBILI_SEARCH_URL = "https://api.bilibili.com/x/web-interface/search/type"
SOGOU_SEARCH_URL = "https://www.sogou.com/web"


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


def fetch_candidates(source: Source, keyword: Keyword, query: str | None = None) -> list[Candidate]:
    source_type = source.source_type.lower()
    query_text = query or keyword.query_template or keyword.keyword
    if source_type == "rss":
        return _fetch_rss(source, keyword, query_text)
    if source_type in {"hacker_news", "hacker-news", "hn"}:
        return _fetch_hacker_news(source, keyword, query_text)
    if source_type in {"x", "twitter", "x_twitter", "x-twitter"}:
        return _fetch_x_twitter(source, keyword, query_text)
    if source_type == "bing":
        return _fetch_bing(source, keyword, query_text)
    if source_type in {"bilibili", "bili"}:
        return _fetch_bilibili(source, keyword, query_text)
    if source_type in {"sogou", "weibo_sogou", "weibo-sogou"}:
        return _fetch_sogou(source, keyword, query_text)
    raise SourceIngestionError(f"Unsupported source_type: {source.source_type}")


def _fetch_rss(source: Source, keyword: Keyword, query: str) -> list[Candidate]:
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
                raw_payload={"source_type": "rss", "feed_url": url, "query": query},
            )
        )
    return candidates


def _fetch_hacker_news(source: Source, keyword: Keyword, query: str) -> list[Candidate]:
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
                        raw_payload={"source_type": "hacker_news", "id": story_id, "score": item.get("score"), "query": query},
                    )
                )
            return candidates
    except Exception as exc:  # noqa: BLE001
        raise SourceIngestionError(f"Hacker News fetch failed for {source.name}: {exc}") from exc


def _fetch_x_twitter(source: Source, keyword: Keyword, query: str) -> list[Candidate]:
    if not settings.x_api_bearer_token:
        raise SourceIngestionError(f"X/Twitter fetch skipped for {source.name}: X_API_BEARER_TOKEN is not configured.")
    limit = max(10, min(int(source.config.get("limit") or settings.source_fetch_limit), 100))
    search_query = str(source.config.get("query_template") or f"{query} -is:retweet -is:reply")
    params = {
        "query": search_query,
        "max_results": limit,
        "tweet.fields": "id,text,created_at,author_id,public_metrics,lang,source",
        "expansions": "author_id",
        "user.fields": "id,name,username,verified",
    }
    headers = {"Authorization": f"Bearer {settings.x_api_bearer_token}"}
    try:
        response = httpx.get(X_SEARCH_URL, headers=headers, params=params, timeout=20)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:  # noqa: BLE001
        raise SourceIngestionError(f"X/Twitter fetch failed for {source.name}: {exc}") from exc
    users = {user.get("id"): user for user in payload.get("includes", {}).get("users", [])}
    candidates: list[Candidate] = []
    for item in payload.get("data", []):
        user = users.get(item.get("author_id"), {})
        username = user.get("username") or item.get("author_id") or "unknown"
        tweet_id = item.get("id")
        text = item.get("text")
        if not tweet_id or not text:
            continue
        candidates.append(
            Candidate(
                title=text[:120],
                url=f"https://x.com/{username}/status/{tweet_id}",
                source_id=source.id,
                keyword_id=keyword.id,
                author=username,
                published_at=_parse_datetime(item.get("created_at")),
                snippet=text,
                raw_payload={"source_type": "x_twitter", "query": search_query, "tweet": item, "user": user},
            )
        )
    return candidates


def _fetch_bing(source: Source, keyword: Keyword, query: str) -> list[Candidate]:
    if not settings.bing_search_api_key:
        raise SourceIngestionError(f"Bing fetch skipped for {source.name}: BING_SEARCH_API_KEY is not configured.")
    limit = min(int(source.config.get("limit") or settings.source_fetch_limit), 50)
    endpoint = str(source.config.get("endpoint") or BING_SEARCH_URL)
    headers = {"Ocp-Apim-Subscription-Key": settings.bing_search_api_key}
    params = {"q": query, "count": limit, "mkt": source.config.get("mkt") or "zh-CN"}
    try:
        response = httpx.get(endpoint, headers=headers, params=params, timeout=20)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:  # noqa: BLE001
        raise SourceIngestionError(f"Bing fetch failed for {source.name}: {exc}") from exc
    candidates: list[Candidate] = []
    for item in payload.get("webPages", {}).get("value", [])[:limit]:
        title = item.get("name")
        url = item.get("url")
        if not title or not url:
            continue
        candidates.append(
            Candidate(
                title=title,
                url=url,
                source_id=source.id,
                keyword_id=keyword.id,
                author=item.get("siteName"),
                published_at=_parse_datetime(item.get("dateLastCrawled")),
                snippet=_strip_html(item.get("snippet")),
                raw_payload={"source_type": "bing", "query": query, "item": item},
            )
        )
    return candidates


def _fetch_bilibili(source: Source, keyword: Keyword, query: str) -> list[Candidate]:
    limit = int(source.config.get("limit") or settings.source_fetch_limit)
    params = {"search_type": "video", "keyword": query, "page": 1}
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = httpx.get(BILIBILI_SEARCH_URL, headers=headers, params=params, timeout=20)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:  # noqa: BLE001
        raise SourceIngestionError(f"Bilibili fetch failed for {source.name}: {exc}") from exc
    candidates: list[Candidate] = []
    for item in payload.get("data", {}).get("result", [])[:limit]:
        title = _strip_html(item.get("title"))
        arcurl = item.get("arcurl") or item.get("url")
        if not title or not arcurl:
            continue
        candidates.append(
            Candidate(
                title=title,
                url=arcurl,
                source_id=source.id,
                keyword_id=keyword.id,
                author=item.get("author"),
                published_at=datetime.fromtimestamp(item["pubdate"], tz=timezone.utc) if item.get("pubdate") else None,
                snippet=_strip_html(item.get("description")),
                raw_payload={"source_type": "bilibili", "query": query, "item": item},
            )
        )
    return candidates


def _fetch_sogou(source: Source, keyword: Keyword, query: str) -> list[Candidate]:
    limit = int(source.config.get("limit") or settings.source_fetch_limit)
    params = {"query": query}
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = httpx.get(SOGOU_SEARCH_URL, headers=headers, params=params, timeout=20)
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        raise SourceIngestionError(f"Sogou fetch failed for {source.name}: {exc}") from exc
    candidates: list[Candidate] = []
    for index, match in enumerate(response.text.split('href="')[1 : limit + 1], start=1):
        url = match.split('"', 1)[0]
        if not url.startswith("http"):
            continue
        title = f"{query} - Sogou result {index}"
        candidates.append(
            Candidate(
                title=title,
                url=url,
                source_id=source.id,
                keyword_id=keyword.id,
                author="Sogou",
                published_at=None,
                snippet=f"Sogou public search result for {query}.",
                raw_payload={"source_type": "sogou", "query": query, "rank": index},
            )
        )
    return candidates


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
