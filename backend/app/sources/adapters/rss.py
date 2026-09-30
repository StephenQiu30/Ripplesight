from __future__ import annotations

import calendar
import hashlib
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, ClassVar, Literal
from urllib.parse import quote, urlsplit

import feedparser
import httpx

from sources.adapters.http_source import (
    HttpSourceAdapter,
    SourceFailureError,
    html_to_text,
    parse_timestamp,
)
from sources.adapters.rsshub_endpoint import is_fixed_rsshub_endpoint
from sources.adapters.web_targets import normalize_web_url
from sources.contracts import (
    SocialSourceCapability,
    SourceCapability,
    SourcePage,
    SourcePageState,
    SourcePost,
    SourceRequest,
    SourceStopReason,
)

_QUERY_PLACEHOLDER = "{query}"
_MAX_EXTERNAL_ID = 512
GOOGLE_NEWS_FEED_URL_TEMPLATE = (
    "https://news.google.com/rss/search?q={query}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
)


def _external_id(entry: Any) -> tuple[str, Literal["guid", "url_fallback"]] | None:
    guid = entry.get("id")
    if isinstance(guid, str) and (guid := guid.strip()):
        if len(guid) > _MAX_EXTERNAL_ID or any(ord(char) < 32 or ord(char) == 127 for char in guid):
            return "guid-sha256:" + hashlib.sha256(guid.encode()).hexdigest(), "guid"
        return guid, "guid"
    link = entry.get("link")
    if not isinstance(link, str):
        return None
    try:
        host = urlsplit(link).hostname
        if host is None:
            return None
        normalized = normalize_web_url(link, allowed_hosts=frozenset({host}))
    except ValueError:
        return None
    fallback = "url:" + normalized
    if len(fallback) > _MAX_EXTERNAL_ID:
        fallback = "url-sha256:" + hashlib.sha256(normalized.encode()).hexdigest()
    return fallback, "url_fallback"


def _published_at(entry: Any) -> object:
    for key in ("published_parsed", "updated_parsed"):
        parsed = entry.get(key)
        if parsed is not None:
            return calendar.timegm(parsed)
    return entry.get("published") or entry.get("updated")


class RssSourceAdapter(HttpSourceAdapter):
    """Keyword search over one RSS/Atom feed template (RSSHub, Google News, Reddit, hnrss).

    A template containing `{query}` receives the URL-encoded query; a template without it
    (for example a hot list) is fetched as-is and filtered later by the topic rules.
    Feeds have no pagination, so every search returns one finite snapshot page.
    """

    capabilities: ClassVar[frozenset[SocialSourceCapability]] = frozenset({SourceCapability.SEARCH})
    adapter_version: ClassVar[str] = "feedparser-6"

    def __init__(
        self,
        *,
        source_key: str,
        feed_url_template: str,
        allowed_hosts: frozenset[str],
        before_request: Callable[[int], bool],
        cancelled: Callable[[], bool] = lambda: False,
        max_requests: int = 1,
        max_seconds: float = 60,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        parsed = urlsplit(feed_url_template)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("feed_url_template must be an http(s) URL")
        super().__init__(
            source_key=source_key,
            allowed_hosts=allowed_hosts,
            before_request=before_request,
            cancelled=cancelled,
            max_requests=max_requests,
            max_seconds=max_seconds,
            transport=transport,
        )
        if parsed.hostname not in self._allowed_hosts:
            raise ValueError("feed_url_template host must be allowlisted")
        if source_key == "rss_36kr" and not is_fixed_rsshub_endpoint(
            feed_url_template,
            route="/36kr/newsflashes",
            allowed_hosts=allowed_hosts,
        ):
            raise ValueError("rss_36kr requires the local RSSHub newsflashes endpoint")
        if source_key == "google_news" and (
            feed_url_template != GOOGLE_NEWS_FEED_URL_TEMPLATE
            or allowed_hosts != frozenset({"news.google.com"})
        ):
            raise ValueError("Google News requires the fixed HTTPS search RSS endpoint")
        self._template = feed_url_template

    def _follow_redirects(self) -> bool:
        return self.source_key not in {"google_news", "rss_36kr"}

    def _fetch(self, request: SourceRequest) -> SourcePage:
        if request.capability is not SourceCapability.SEARCH or request.page_token is not None:
            raise SourceFailureError(SourceStopReason.UNSUPPORTED)
        assert request.capability is SourceCapability.SEARCH
        url = self._template.replace(_QUERY_PLACEHOLDER, quote(request.query, safe=""))
        feed = feedparser.parse(self._get_bytes(url))
        if not feed.get("version") or feed.get("bozo"):
            raise SourceFailureError(SourceStopReason.PROTOCOL_ERROR)
        feed_updated_at = parse_timestamp(_published_at(feed.feed))
        items: list[SourcePost] = []
        seen: set[str] = set()
        for entry in feed.get("entries", []):
            identity = _external_id(entry)
            if identity is None or identity[0] in seen:
                continue
            external_id, identity_basis = identity
            seen.add(external_id)
            title = html_to_text(entry.get("title"))
            summary = entry.get("summary")
            if not summary and entry.get("content"):
                summary = entry["content"][0].get("value")
            text = html_to_text(summary)
            link = entry.get("link")
            author = entry.get("author")
            items.append(
                SourcePost(
                    source_key=self.source_key,
                    external_id=external_id,
                    identity_basis=identity_basis,
                    author_external_id=None,
                    author_name=author[:256] if isinstance(author, str) and author else None,
                    published_at=parse_timestamp(_published_at(entry)),
                    title=title[:2000] if title else None,
                    text=text[:100_000] if text else None,
                    text_scope="truncated" if text else None,
                    like_count=None,
                    comment_count=None,
                    repost_count=None,
                    canonical_url=(
                        link
                        if isinstance(link, str)
                        and link.startswith(("http://", "https://"))
                        and len(link) <= 2048
                        else None
                    ),
                )
            )
        if feed.entries and not items:
            raise SourceFailureError(SourceStopReason.PROTOCOL_ERROR)
        if len(items) > request.page_size:
            return SourcePage(
                source_key=self.source_key,
                capability=request.capability,
                state=SourcePageState.PARTIAL,
                items=tuple(items[: request.page_size]),
                next_page_token=None,
                watermark=None,
                stop_reason=SourceStopReason.BUDGET_EXHAUSTED,
                observed_at=datetime.now(UTC),
                adapter_version=self.adapter_version,
                source_feed_updated_at=feed_updated_at,
            )
        return self._page(request, tuple(items), None).model_copy(
            update={"source_feed_updated_at": feed_updated_at}
        )
