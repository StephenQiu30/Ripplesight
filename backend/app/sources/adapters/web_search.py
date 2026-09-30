from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from datetime import UTC, datetime
from typing import ClassVar
from urllib.parse import urlsplit

import httpx

from sources.adapters.http_source import (
    HttpSourceAdapter,
    SourceFailureError,
    html_to_text,
    parse_timestamp,
)
from sources.adapters.web_targets import normalize_public_article_url
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
SEARXNG_HOSTS = frozenset({"127.0.0.1", "host.docker.internal"})
_ENGINE = "duckduckgo news"


def configured_searxng_host() -> str:
    host = os.environ.get("HOTKEY_SEARXNG_HOST", "127.0.0.1")
    if host not in SEARXNG_HOSTS:
        raise ValueError("HOTKEY_SEARXNG_HOST must be a fixed local SearXNG host")
    return host


def _published_at(value: object) -> datetime | None:
    """SearXNG runs with TZ=UTC and emits naive ISO timestamps, so naive means UTC."""
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=UTC)
        except ValueError:
            pass
    return parse_timestamp(value)


def _article_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return normalize_public_article_url(value)
    except ValueError:
        return None


def _failure_details(payload: dict[str, object]) -> tuple[tuple[str, ...], str | None]:
    raw_unresponsive = payload.get("unresponsive_engines", [])
    if not isinstance(raw_unresponsive, list) or len(raw_unresponsive) > 8:
        raise SourceFailureError(SourceStopReason.PROTOCOL_ERROR)
    failures: list[str] = []
    for item in raw_unresponsive:
        if (
            not isinstance(item, list | tuple)
            or len(item) < 2
            or not isinstance(item[0], str)
            or not isinstance(item[1], str)
        ):
            raise SourceFailureError(SourceStopReason.PROTOCOL_ERROR)
        failures.append(f"{item[0][:64]}: {item[1][:60]}")
    raw_error = payload.get("error")
    if raw_error is not None and not isinstance(raw_error, str):
        raise SourceFailureError(SourceStopReason.PROTOCOL_ERROR)
    return tuple(failures), raw_error[:128] if raw_error else None


class WebSearchAdapter(HttpSourceAdapter):
    """One bounded local SearXNG news search with URL fallback identity."""

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
        engines: str = _ENGINE,
        source_key: str = "web",
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        super().__init__(
            source_key=source_key,
            allowed_hosts=allowed_hosts,
            before_request=before_request,
            cancelled=cancelled,
            max_requests=max_requests,
            max_seconds=max_seconds,
            transport=transport,
        )
        if urlsplit(base_url).hostname not in self._allowed_hosts:
            raise ValueError("base_url host must be allowlisted")
        endpoint = base_url.removesuffix("/")
        if not any(
            endpoint == f"http://{host}:8888" and self._allowed_hosts == frozenset({host})
            for host in SEARXNG_HOSTS
        ):
            raise ValueError("SearXNG requires the fixed local search endpoint")
        if engines != _ENGINE:
            raise ValueError("SearXNG requires the duckduckgo news engine")
        self._search_url = f"{endpoint}/search"
        self._engines = engines
        self._page_fingerprints: set[tuple[str, ...]] = set()

    def _follow_redirects(self) -> bool:
        return False

    def _fetch(self, request: SourceRequest) -> SourcePage:
        if not isinstance(request, SearchRequest):
            raise SourceFailureError(SourceStopReason.UNSUPPORTED)
        page_number = 1
        if request.page_token is not None:
            if not request.page_token.isdigit():
                raise SourceFailureError(SourceStopReason.PROTOCOL_ERROR)
            page_number = int(request.page_token)
        if page_number < 1 or page_number > _MAX_PAGES:
            raise SourceFailureError(SourceStopReason.CURSOR_EXPIRED)
        params = {
            "q": request.query,
            "format": "json",
            "pageno": str(page_number),
            "engines": self._engines,
        }
        try:
            raw = self._get_bytes(self._search_url, params=params)
        except httpx.TimeoutException:
            return self._stopped(request, SourceStopReason.UPSTREAM_ERROR).model_copy(
                update={"source_page_number": page_number, "source_search_error": "timeout"}
            )
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return self._stopped(request, SourceStopReason.PROTOCOL_ERROR).model_copy(
                update={"source_page_number": page_number, "source_search_error": "invalid_json"}
            )
        results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(results, list):
            raise SourceFailureError(SourceStopReason.PROTOCOL_ERROR)
        assert isinstance(payload, dict)
        failures, search_error = _failure_details(payload)
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
            if len(items) >= request.page_size:
                break
        metadata = {
            "source_engine": _ENGINE if results else None,
            "source_page_number": page_number,
            "source_unresponsive_engines": failures,
            "source_search_error": search_error,
        }
        if failures or search_error:
            if not items:
                return self._stopped(request, SourceStopReason.UPSTREAM_ERROR).model_copy(
                    update=metadata
                )
            return SourcePage(
                source_key=self.source_key,
                capability=request.capability,
                state=SourcePageState.PARTIAL,
                items=tuple(items),
                next_page_token=None,
                watermark=None,
                stop_reason=SourceStopReason.UPSTREAM_ERROR,
                observed_at=datetime.now(UTC),
                adapter_version=self.adapter_version,
            ).model_copy(update=metadata)
        if results and not items:
            return self._stopped(request, SourceStopReason.PROTOCOL_ERROR).model_copy(
                update=metadata
            )
        fingerprint = tuple(sorted(seen))
        if fingerprint and fingerprint in self._page_fingerprints:
            return self._stopped(request, SourceStopReason.CURSOR_LOOP).model_copy(update=metadata)
        if fingerprint:
            self._page_fingerprints.add(fingerprint)
        page_overflow = len(results) > request.page_size
        can_continue = len(results) >= request.page_size
        if can_continue and (
            page_overflow or page_number >= _MAX_PAGES or self._request_count >= self._max_requests
        ):
            return SourcePage(
                source_key=self.source_key,
                capability=request.capability,
                state=SourcePageState.PARTIAL,
                items=tuple(items),
                next_page_token=None,
                watermark=None,
                stop_reason=SourceStopReason.BUDGET_EXHAUSTED,
                observed_at=datetime.now(UTC),
                adapter_version=self.adapter_version,
            ).model_copy(update=metadata)
        page = self._page(request, tuple(items), str(page_number + 1) if can_continue else None)
        return page.model_copy(update=metadata)

    def _post(self, result: object) -> SourcePost | None:
        if not isinstance(result, dict):
            raise SourceFailureError(SourceStopReason.PROTOCOL_ERROR)
        url = _article_url(result.get("url"))
        if url is None:
            return None
        title = result.get("title") if isinstance(result.get("title"), str) else None
        text = html_to_text(result.get("content"))
        return SourcePost(
            source_key=self.source_key,
            external_id="url:" + hashlib.sha256(url.encode()).hexdigest(),
            identity_basis="url_fallback",
            author_external_id=None,
            published_at=_published_at(result.get("publishedDate")),
            title=title[:2000] if title else None,
            text=text,
            text_scope="truncated" if text else None,
            like_count=None,
            comment_count=None,
            repost_count=None,
            canonical_url=url,
        )
