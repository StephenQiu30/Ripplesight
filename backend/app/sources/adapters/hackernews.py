from __future__ import annotations

import json
import math
from collections.abc import Callable
from typing import Any, ClassVar
from urllib.parse import quote, urlsplit

import httpx

from sources.adapters.http_source import (
    HttpSourceAdapter,
    SourceFailureError,
    html_to_text,
    parse_timestamp,
)
from sources.contracts import (
    CommentsRequest,
    SearchRequest,
    SocialSourceCapability,
    SourceCapability,
    SourceComment,
    SourcePage,
    SourcePost,
    SourceRequest,
    SourceSort,
    SourceStopReason,
    SourceTerminalEvidence,
)

_API = "https://hn.algolia.com/api/v1"
_ITEM_URL = "https://news.ycombinator.com/item?id={id}"
_MAX_PAGES = 50


def _hn_id(value: object) -> str:
    text = str(value) if isinstance(value, int) and not isinstance(value, bool) else value
    if not isinstance(text, str) or not text.isascii() or not text.isdigit() or len(text) > 12:
        raise SourceFailureError(SourceStopReason.PROTOCOL_ERROR)
    return text


def _story_id(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 512
        or value != value.strip()
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise SourceFailureError(SourceStopReason.PROTOCOL_ERROR)
    return value


def _count(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


class HackerNewsAdapter(HttpSourceAdapter):
    """Hacker News through the public Algolia API: story search and full comment trees.

    Comments of one story are fetched once as a tree, flattened in reply order and served
    in pages whose token is the next offset; each comment keeps its parent comment ID.
    """

    capabilities: ClassVar[frozenset[SocialSourceCapability]] = frozenset(
        {SourceCapability.SEARCH, SourceCapability.COMMENTS}
    )
    adapter_version: ClassVar[str] = "hn-algolia-v1"

    def __init__(
        self,
        *,
        before_request: Callable[[int], bool],
        base_url: str = _API,
        allowed_hosts: frozenset[str] = frozenset({"hn.algolia.com"}),
        cancelled: Callable[[], bool] = lambda: False,
        max_requests: int = 10,
        max_seconds: float = 60,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        try:
            parsed = urlsplit(base_url)
            port = parsed.port
        except ValueError as error:
            raise ValueError("Hacker News requires the fixed HTTPS Algolia API") from error
        if (
            parsed.scheme != "https"
            or parsed.hostname != "hn.algolia.com"
            or port is not None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path.rstrip("/") != "/api/v1"
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Hacker News requires the fixed HTTPS Algolia API")
        super().__init__(
            source_key="hackernews",
            allowed_hosts=allowed_hosts,
            before_request=before_request,
            cancelled=cancelled,
            max_requests=max_requests,
            max_seconds=max_seconds,
            transport=transport,
        )
        if "hn.algolia.com" not in self._allowed_hosts:
            raise ValueError("Algolia API host must be allowlisted")
        self._api = _API
        self._comment_cache: tuple[SourceComment, ...] | None = None

    def _follow_redirects(self) -> bool:
        # A redirect can discard or replace the bounded numericFilters query.
        return False

    def _require_allowed_url(self, url: str) -> None:
        super()._require_allowed_url(url)
        parsed = urlsplit(url)
        path = parsed.path
        item_prefix = "/api/v1/items/"
        item_id = path[len(item_prefix) :] if path.startswith(item_prefix) else None
        if (
            parsed.scheme != "https"
            or parsed.hostname != "hn.algolia.com"
            or parsed.port is not None
            or parsed.fragment
            or not (
                path in {"/api/v1/search", "/api/v1/search_by_date"}
                or (item_id is not None and item_id.isascii() and item_id.isdigit())
            )
        ):
            raise SourceFailureError(SourceStopReason.ACCESS_DENIED)

    def _fetch(self, request: SourceRequest) -> SourcePage:
        if isinstance(request, SearchRequest):
            return self._search(request)
        if isinstance(request, CommentsRequest):
            return self._comments(request)
        raise SourceFailureError(SourceStopReason.UNSUPPORTED)

    def _json(self, url: str, params: dict[str, str] | None = None) -> Any:
        return json.loads(self._get_bytes(url, params=params))

    def _search(self, request: SearchRequest) -> SourcePage:
        page_index = 0
        if request.page_token is not None:
            if not request.page_token.isdigit():
                raise SourceFailureError(SourceStopReason.PROTOCOL_ERROR)
            page_index = int(request.page_token)
        if page_index >= _MAX_PAGES:
            raise SourceFailureError(SourceStopReason.CURSOR_EXPIRED)
        params = {
            "query": request.query,
            "tags": "story",
            "hitsPerPage": str(request.page_size),
            "page": str(page_index),
        }
        if request.starts_at is not None and request.ends_at is not None:
            params["numericFilters"] = (
                f"created_at_i>={math.ceil(request.starts_at.timestamp())},"
                f"created_at_i<{math.ceil(request.ends_at.timestamp())}"
            )
        endpoint = "search_by_date" if request.sort is SourceSort.LATEST else "search"
        payload = self._json(f"{self._api}/{endpoint}", params)
        if not isinstance(payload, dict) or not isinstance(payload.get("hits"), list):
            raise SourceFailureError(SourceStopReason.PROTOCOL_ERROR)
        hits = payload["hits"]
        if len(hits) > request.page_size:
            raise SourceFailureError(SourceStopReason.PROTOCOL_ERROR)
        pages = payload.get("nbPages")
        if type(pages) is not int or pages < 0:
            raise SourceFailureError(SourceStopReason.PROTOCOL_ERROR)
        if pages == 0 and hits:
            raise SourceFailureError(SourceStopReason.PROTOCOL_ERROR)
        for key in ("page", "hitsPerPage", "nbHits"):
            value = payload.get(key)
            if value is not None and (type(value) is not int or value < 0):
                raise SourceFailureError(SourceStopReason.PROTOCOL_ERROR)
        if ("page" in payload and payload["page"] != page_index) or (
            "hitsPerPage" in payload and payload["hitsPerPage"] != request.page_size
        ):
            raise SourceFailureError(SourceStopReason.PROTOCOL_ERROR)
        exhaustive = payload.get("exhaustiveNbHits")
        if exhaustive is not None and type(exhaustive) is not bool:
            raise SourceFailureError(SourceStopReason.PROTOCOL_ERROR)
        items = tuple(self._post(hit) for hit in hits)
        has_more = page_index + 1 < min(pages, _MAX_PAGES)
        page = self._page(request, items, str(page_index + 1) if has_more else None)
        if has_more or request.starts_at is None or request.ends_at is None:
            return page
        total = payload.get("nbHits")
        verified = (
            payload.get("page") == page_index
            and payload.get("hitsPerPage") == request.page_size
            and type(total) is int
            and exhaustive is True
            and pages == math.ceil(total / request.page_size)
            and pages <= _MAX_PAGES
            and ((pages == 0 and page_index == 0) or page_index == pages - 1)
            and len(hits) == max(total - page_index * request.page_size, 0)
        )
        evidence = SourceTerminalEvidence(
            starts_at=request.starts_at,
            ends_at=request.ends_at,
            sort_key=request.sort,
            query_bounded=True,
            sort_applied=True,
            terminal_verified=verified,
        )
        return page.model_copy(update={"terminal_evidence": evidence})

    def _post(self, hit: object) -> SourcePost:
        if not isinstance(hit, dict):
            raise SourceFailureError(SourceStopReason.PROTOCOL_ERROR)
        identifier = _story_id(hit.get("objectID"))
        author = hit.get("author") if isinstance(hit.get("author"), str) else None
        title = hit.get("title") if isinstance(hit.get("title"), str) else None
        text = (
            html_to_text(hit.get("story_text")) if isinstance(hit.get("story_text"), str) else None
        )
        created_at = hit.get("created_at_i")
        if created_at is None:
            created_at = hit.get("created_at")
        try:
            published_at = parse_timestamp(created_at)
        except (OverflowError, OSError) as error:
            raise SourceFailureError(SourceStopReason.PROTOCOL_ERROR) from error
        return SourcePost(
            source_key=self.source_key,
            external_id=identifier,
            author_external_id=author or None,
            author_name=author or None,
            published_at=published_at,
            title=title or None,
            text=text,
            like_count=_count(hit.get("points")),
            comment_count=_count(hit.get("num_comments")),
            repost_count=None,
            canonical_url=_ITEM_URL.format(id=quote(identifier, safe="")),
        )

    def _comments(self, request: CommentsRequest) -> SourcePage:
        story_id = _hn_id(request.post_external_id)
        offset = 0
        if request.page_token is not None:
            if not request.page_token.isdigit():
                raise SourceFailureError(SourceStopReason.PROTOCOL_ERROR)
            offset = int(request.page_token)
        if self._comment_cache is None:
            tree = self._json(f"{self._api}/items/{story_id}")
            if not isinstance(tree, dict) or _hn_id(tree.get("id")) != story_id:
                raise SourceFailureError(SourceStopReason.PROTOCOL_ERROR)
            flattened: list[SourceComment] = []
            self._flatten(tree.get("children"), story_id, None, flattened)
            self._comment_cache = tuple(flattened)
        page = self._comment_cache[offset : offset + request.page_size]
        next_offset = offset + len(page)
        return self._page(
            request,
            page,
            str(next_offset) if next_offset < len(self._comment_cache) else None,
        )

    def _flatten(
        self,
        children: object,
        story_id: str,
        parent_id: str | None,
        out: list[SourceComment],
    ) -> None:
        if children is None:
            return
        if not isinstance(children, list):
            raise SourceFailureError(SourceStopReason.PROTOCOL_ERROR)
        for child in children:
            if not isinstance(child, dict) or child.get("type") != "comment":
                continue
            identifier = _hn_id(child.get("id"))
            text = html_to_text(child.get("text"))
            author = child.get("author") if isinstance(child.get("author"), str) else None
            if text is not None:
                out.append(
                    SourceComment(
                        source_key=self.source_key,
                        external_id=identifier,
                        post_external_id=story_id,
                        parent_comment_external_id=parent_id,
                        author_external_id=author or None,
                        author_name=author or None,
                        published_at=parse_timestamp(
                            child.get("created_at_i") or child.get("created_at")
                        ),
                        text=text,
                        like_count=_count(child.get("points")),
                        canonical_url=_ITEM_URL.format(id=identifier),
                    )
                )
            self._flatten(child.get("children"), story_id, identifier, out)
