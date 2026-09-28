from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime
from typing import ClassVar
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from sources.adapters.http_source import (
    HttpSourceAdapter,
    SourceFailureError,
    html_to_text,
    parse_timestamp,
)
from sources.adapters.web_targets import normalize_web_url
from sources.contracts import (
    SearchRequest,
    SocialSourceCapability,
    SourceCapability,
    SourcePage,
    SourcePageState,
    SourcePost,
    SourceRequest,
    SourceStopReason,
)

_MAX_PAGES = 5
_ENGINE = "duckduckgo news"
_TRACKING_PARAMETERS = frozenset({"fbclid", "gclid", "dclid", "msclkid", "igshid"})


def _article_url(value: object) -> str | None:
    if not isinstance(value, str) or len(value) > 2048:
        return None
    try:
        host = urlsplit(value).hostname
        if host is None:
            return None
        normalized = normalize_web_url(value, allowed_hosts=frozenset({host}))
    except ValueError:
        return None
    parsed = urlsplit(normalized)
    query = urlencode(
        [
            (key, item)
            for key, item in parse_qsl(parsed.query, keep_blank_values=True)
            if not key.lower().startswith("utm_") and key.lower() not in _TRACKING_PARAMETERS
        ]
    )
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, ""))


def _published_at(value: object) -> datetime | None:
    """SearXNG runs with TZ=UTC and emits naive ISO timestamps, so naive means UTC."""
    if isinstance(value, str):
        with suppress(ValueError):
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=UTC)
    return parse_timestamp(value)


class WebSearchAdapter(HttpSourceAdapter):
    """Keyword news search through the self-hosted SearXNG JSON API (DEC-001-107).

    Results use a normalized article URL identity. Unknown publication dates remain
    unknown; discovery records their first observation separately.
    """

    capabilities: ClassVar[frozenset[SocialSourceCapability]] = frozenset({SourceCapability.SEARCH})
    adapter_version: ClassVar[str] = "searxng-json-news"

    def __init__(
        self,
        *,
        base_url: str,
        allowed_hosts: frozenset[str],
        before_request: Callable[[int], bool],
        cancelled: Callable[[], bool] = lambda: False,
        max_requests: int = _MAX_PAGES,
        max_seconds: float = 60,
        categories: str = "news",
        engines: str = "duckduckgo news",
        source_key: str = "web",
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        parsed = urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("base_url must be an http(s) URL")
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
            raise ValueError("base_url host must be allowlisted")
        if base_url.rstrip("/") != "http://127.0.0.1:8888" or allowed_hosts != frozenset(
            {"127.0.0.1"}
        ):
            raise ValueError("news search requires the local SearXNG endpoint")
        self._search_url = base_url.rstrip("/") + "/search"
        if engines != _ENGINE:
            raise ValueError("news search requires duckduckgo news")
        self._categories = categories
        self._engines = engines
        self._seen_articles: set[str] = set()
        self._diagnostic: str | None = None

    def _fetch(self, request: SourceRequest) -> SourcePage:
        if not isinstance(request, SearchRequest):
            raise SourceFailureError(SourceStopReason.UNSUPPORTED)
        page_number = 1
        if request.page_token is not None:
            if not request.page_token.isdigit():
                raise SourceFailureError(SourceStopReason.PROTOCOL_ERROR)
            page_number = int(request.page_token)
        if not 1 <= page_number <= _MAX_PAGES:
            raise SourceFailureError(SourceStopReason.PROTOCOL_ERROR)
        params = {"q": request.query, "format": "json", "pageno": str(page_number)}
        # SearXNG adds category engines to explicit engines, so send only one of them.
        if self._engines:
            params["engines"] = self._engines
        else:
            params["categories"] = self._categories
        try:
            payload = json.loads(self._get_bytes(self._search_url, params=params))
        except httpx.TimeoutException:
            self._diagnostic = "request_timeout"
            raise
        results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(results, list):
            raise SourceFailureError(SourceStopReason.PROTOCOL_ERROR)
        if "query" in payload and payload["query"] != request.query:
            raise SourceFailureError(SourceStopReason.PROTOCOL_ERROR)
        unresponsive = payload.get("unresponsive_engines", [])
        if not isinstance(unresponsive, list):
            raise SourceFailureError(SourceStopReason.PROTOCOL_ERROR)
        failed = bool(payload.get("error")) or bool(unresponsive)
        if failed:
            if unresponsive:
                timed_out = any(
                    isinstance(entry, list | tuple)
                    and len(entry) > 1
                    and isinstance(entry[1], str)
                    and "timeout" in entry[1].lower()
                    for entry in unresponsive
                )
                self._diagnostic = "engine_timeout" if timed_out else "engine_unresponsive"
            else:
                self._diagnostic = "searxng_error"
        items: list[SourcePost] = []
        seen: set[str] = set()
        for result in results:
            if not isinstance(result, dict) or result.get("engine") != _ENGINE:
                raise SourceFailureError(SourceStopReason.PROTOCOL_ERROR)
            post = self._post(result)
            if post is None or post.external_id in seen:
                continue
            seen.add(post.external_id)
            items.append(post)
        page_truncated = len(items) > request.page_size
        items = items[: request.page_size]
        previous_articles = self._seen_articles.copy()
        repeated = bool(seen & previous_articles)
        self._seen_articles.update(seen)
        if repeated:
            items = [item for item in items if item.external_id not in previous_articles]
            self._diagnostic = "repeated_page"
            return self._source_terminal(request, tuple(items), SourceStopReason.CURSOR_LOOP)
        if failed:
            return self._source_terminal(request, tuple(items), SourceStopReason.UPSTREAM_ERROR)
        if page_truncated:
            self._diagnostic = "page_size_limit"
            return self._source_terminal(request, tuple(items), SourceStopReason.BUDGET_EXHAUSTED)
        if page_number == _MAX_PAGES and results:
            self._diagnostic = "page_limit"
            return self._source_terminal(request, tuple(items), SourceStopReason.BUDGET_EXHAUSTED)
        has_more = bool(results) and page_number < _MAX_PAGES
        page = self._page(request, tuple(items), str(page_number + 1) if has_more else None)
        return page.model_copy(
            update={
                "source_engine": _ENGINE,
                "source_actual_engine": _ENGINE if results else None,
            }
        )

    def _source_terminal(
        self,
        request: SearchRequest,
        items: tuple[SourcePost, ...],
        reason: SourceStopReason,
    ) -> SourcePage:
        return SourcePage(
            source_key=self.source_key,
            capability=request.capability,
            state=SourcePageState.PARTIAL if items else SourcePageState.STOPPED,
            items=items,
            next_page_token=None,
            watermark=None,
            stop_reason=reason,
            observed_at=datetime.now(UTC),
            adapter_version=self.adapter_version,
            source_engine=_ENGINE,
            source_actual_engine=_ENGINE if items else None,
            source_diagnostic=self._diagnostic,
        )

    def _stopped(
        self,
        request: SourceRequest,
        reason: SourceStopReason,
        retry_at: datetime | None = None,
    ) -> SourcePage:
        return (
            super()
            ._stopped(request, reason, retry_at)
            .model_copy(update={"source_engine": _ENGINE, "source_diagnostic": self._diagnostic})
        )

    def _post(self, result: object) -> SourcePost | None:
        if not isinstance(result, dict):
            raise SourceFailureError(SourceStopReason.PROTOCOL_ERROR)
        url = _article_url(result.get("url"))
        if url is None:
            return None
        title = result.get("title") if isinstance(result.get("title"), str) else None
        text = html_to_text(result.get("content"))
        native = result.get("id")
        if isinstance(native, str) and native.strip():
            native_id = native.strip()
        elif isinstance(native, int) and not isinstance(native, bool):
            native_id = str(native)
        else:
            native_id = None
        if native_id is not None:
            external_id = "native:" + native_id
            if len(external_id) > 512 or any(
                ord(char) < 32 or ord(char) == 127 for char in external_id
            ):
                external_id = "native-sha256:" + hashlib.sha256(native_id.encode()).hexdigest()
        else:
            external_id = "url-sha256:" + hashlib.sha256(url.encode()).hexdigest()
        return SourcePost(
            source_key=self.source_key,
            external_id=external_id,
            identity_basis="guid" if native_id is not None else "url_fallback",
            author_external_id=None,
            published_at=_published_at(result.get("publishedDate")),
            title=title[:2000] if title else None,
            text=text[:100_000] if text else None,
            text_scope="truncated" if text else None,
            like_count=None,
            comment_count=None,
            repost_count=None,
            canonical_url=url,
        )
