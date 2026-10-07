"""Small, bounded Bilibili POC using the operator's existing Chrome session."""

from __future__ import annotations

import base64
import html
import math
import re
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, ClassVar
from uuid import uuid4

import httpx

from sources.contracts import (
    CommentsRequest,
    SearchRequest,
    SocialSourceCapability,
    SourceCapability,
    SourceComment,
    SourcePage,
    SourcePageState,
    SourcePost,
    SourceRequest,
    SourceSort,
    SourceStopReason,
)

VERSION = "bilibili-chrome-poc-1"
API = "https://api.bilibili.com"


class CollectionStoppedError(Exception):
    """Only stable codes may escape the authenticated HTTP boundary."""


def chrome_cookies(identity_env: Path, client: httpx.Client) -> httpx.Cookies:
    """Read only the local bridge settings, never export account material."""
    if identity_env.is_symlink() or identity_env.stat().st_mode & 0o077:
        raise CollectionStoppedError("identity_file_not_private")
    config = {}
    for line in identity_env.read_text().splitlines():
        key, separator, value = line.partition("=")
        if separator and key.strip() in {"COOKIE_SOURCE_TOKEN", "COOKIE_SOURCE_PORT"}:
            config[key.strip()] = value.strip().strip('"').strip("'")
    token = config.get("COOKIE_SOURCE_TOKEN")
    port = int(config.get("COOKIE_SOURCE_PORT", "19101"))
    if not token or not 1024 <= port <= 65535:
        raise CollectionStoppedError("identity_configuration_invalid")
    response = client.post(
        f"http://127.0.0.1:{port}/cookies",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "site": "bilibili",
            "task_id": f"ripplesight-{uuid4().hex}",
            "deadline": (datetime.now(UTC) + timedelta(seconds=20)).isoformat(),
        },
    )
    if response.status_code != 200:
        raise CollectionStoppedError("chrome_session_unavailable")
    data = response.json()
    raw = base64.b64decode(data["cookies"], validate=True)
    # The bridge digest is an opaque account HMAC, not a checksum of this jar.
    if len(raw) > 65536 or not re.fullmatch(r"[0-9a-f]{64}", data["digest"]):
        raise CollectionStoppedError("identity_payload_invalid")
    cookies = httpx.Cookies()
    for line in raw.decode().splitlines():
        line = line.removeprefix("#HttpOnly_")
        if not line or line.startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) != 7:
            raise CollectionStoppedError("identity_payload_invalid")
        domain, _, path, _, _, name, value = fields
        if domain.lstrip(".") not in {"bilibili.com", "www.bilibili.com", "api.bilibili.com"}:
            continue
        cookies.set(name, value, domain=domain, path=path)
    if not any(cookie.name == "SESSDATA" for cookie in cookies.jar):
        raise CollectionStoppedError("chrome_login_required")
    return cookies


def plain(value: object) -> str:
    return html.unescape(re.sub(r"<[^>]*>", "", str(value or "")))


def collect(
    *,
    identity_env: Path,
    keyword: str,
    starts_at: datetime,
    ends_at: datetime,
    charge: Callable[[], None],
    transport: httpx.BaseTransport | None = None,
    deadline_seconds: float = 120,
    include_comments: bool = True,
    comment_post: str | None = None,
    max_posts: int = 2,
    sort: SourceSort = SourceSort.LATEST,
) -> tuple[list[SourcePost], list[SourceComment], int]:
    """One search page, at most two posts and one fresh comment page per post."""
    deadline = time.monotonic() + deadline_seconds
    posts: list[SourcePost] = []
    comments: list[SourceComment] = []
    try:
        with httpx.Client(timeout=20, trust_env=False, transport=transport) as bridge:
            cookies = chrome_cookies(identity_env, bridge)
        with httpx.Client(
            timeout=20,
            trust_env=False,
            follow_redirects=False,
            transport=transport,
            cookies=cookies,
            headers={"Referer": "https://www.bilibili.com/", "User-Agent": "Mozilla/5.0"},
        ) as client:

            def get(path: str, params: dict[str, str | int] | None = None) -> dict[str, Any]:
                if time.monotonic() >= deadline:
                    raise CollectionStoppedError("collection_deadline_exceeded")
                charge()
                with client.stream("GET", API + path, params=params) as response:
                    if response.status_code in {401, 403, 412, 429}:
                        raise CollectionStoppedError("source_access_or_rate_limited")
                    if response.status_code != 200:
                        raise CollectionStoppedError("source_http_error")
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        if time.monotonic() >= deadline:
                            raise CollectionStoppedError("collection_deadline_exceeded")
                        body.extend(chunk)
                        if len(body) > 2 * 1024 * 1024:
                            raise CollectionStoppedError("source_response_too_large")
                import json

                payload = json.loads(body)
                if payload.get("code") in {-101, -111}:
                    raise CollectionStoppedError("chrome_login_required")
                if payload.get("code") in {-352, -412, -509, -403, 412}:
                    raise CollectionStoppedError("source_access_or_rate_limited")
                if payload.get("code") != 0 or not isinstance(payload.get("data"), dict):
                    raise CollectionStoppedError("source_protocol_error")
                return dict(payload["data"])

            if get("/x/web-interface/nav").get("isLogin") is not True:
                raise CollectionStoppedError("chrome_login_required")
            if comment_post is None:
                result = get(
                    "/x/web-interface/wbi/search/type",
                    {
                        "search_type": "video",
                        "keyword": keyword,
                        "order": "pubdate" if sort is SourceSort.LATEST else "click",
                        "page": 1,
                        "page_size": 5,
                        "pubtime_begin_s": int(starts_at.timestamp()),
                        "pubtime_end_s": math.ceil(ends_at.timestamp()) - 1,
                    },
                )
                candidates = result.get("result", [])
            else:
                candidates = [{"aid": comment_post}]
            for row in candidates[:5]:
                aid = str(int(row["aid"]))
                if comment_post is None:
                    timestamp = datetime.fromtimestamp(int(row["pubdate"]), UTC)
                    title, description = plain(row.get("title")), plain(row.get("description"))
                    if not starts_at <= timestamp < ends_at:
                        continue
                    if keyword.casefold() not in (title + " " + description).casefold():
                        continue
                    post = SourcePost(
                        source_key="bilibili",
                        external_id=aid,
                        author_external_id=str(row["mid"]),
                        published_at=timestamp,
                        title=title,
                        text=description,
                        author_name=plain(row.get("author")) or None,
                        like_count=None,
                        comment_count=None,
                        repost_count=None,
                        canonical_url=f"https://www.bilibili.com/video/av{aid}",
                        text_scope="truncated",
                    )
                    posts.append(post)
                if not include_comments:
                    if len(posts) >= max_posts:
                        break
                    continue
                reply_data = get(
                    "/x/v2/reply", {"type": 1, "oid": aid, "pn": 1, "ps": 20, "sort": 0}
                )
                for reply in (reply_data.get("replies") or [])[:20]:
                    # This endpoint's top-level list contains roots; replies are not traversed.
                    if int(reply.get("root", 0)) != 0 or int(reply.get("parent", 0)) != 0:
                        raise CollectionStoppedError("comment_parent_unexpected")
                    comment_id = str(int(reply["rpid"]))
                    comments.append(
                        SourceComment(
                            source_key="bilibili",
                            external_id=comment_id,
                            post_external_id=aid,
                            parent_comment_external_id=None,
                            root_comment_external_id=comment_id,
                            parent_relation_status="root",
                            author_external_id=str(reply["mid"]),
                            published_at=datetime.fromtimestamp(int(reply["ctime"]), UTC),
                            text=str(reply["content"]["message"]),
                            like_count=int(reply["like"]),
                            canonical_url=f"https://www.bilibili.com/video/av{aid}#reply{comment_id}",
                        )
                    )
                if len(posts) >= max_posts:
                    break
            return posts, comments, len(candidates)
    except CollectionStoppedError:
        raise
    except (httpx.HTTPError, ValueError, KeyError, TypeError, OSError, OverflowError):
        raise CollectionStoppedError("collection_transport_or_payload_error") from None


class BilibiliChromeAdapter:
    """Fresh, bounded pages through the local Chrome bridge; never claims full coverage."""

    capabilities: ClassVar[frozenset[SocialSourceCapability]] = frozenset(
        {SourceCapability.SEARCH, SourceCapability.COMMENTS}
    )
    source_key = "bilibili"
    adapter_version: ClassVar[str] = VERSION

    def __init__(
        self,
        *,
        identity_env: Path,
        before_request: Callable[[int], bool],
        cancelled: Callable[[], bool],
        max_requests: int,
        max_seconds: float,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._identity_env = identity_env
        self._before_request = before_request
        self._cancelled = cancelled
        self._remaining = max_requests
        self._started = 0
        self._deadline = time.monotonic() + max_seconds
        self._transport = transport

    def fetch_page(self, request: SourceRequest) -> SourcePage:
        count = 0

        def charge() -> None:
            nonlocal count
            if self._cancelled():
                raise CollectionStoppedError("cancelled")
            if time.monotonic() >= self._deadline or self._remaining <= 0:
                raise CollectionStoppedError("budget_exhausted")
            if not self._before_request(self._started + 1):
                raise CollectionStoppedError("budget_exhausted")
            self._started += 1
            self._remaining -= 1
            count += 1

        items: tuple[SourcePost | SourceComment, ...] = ()
        reason = SourceStopReason.BUDGET_EXHAUSTED
        state = SourcePageState.PARTIAL
        try:
            if request.source_key != "bilibili" or request.page_token is not None:
                raise CollectionStoppedError("unsupported")
            if self._cancelled():
                raise CollectionStoppedError("cancelled")
            if isinstance(request, SearchRequest):
                if request.starts_at is None or request.ends_at is None:
                    raise CollectionStoppedError("unsupported")
                posts, _, _ = collect(
                    identity_env=self._identity_env,
                    keyword=request.query,
                    starts_at=request.starts_at,
                    ends_at=request.ends_at,
                    charge=charge,
                    transport=self._transport,
                    deadline_seconds=max(0.0, self._deadline - time.monotonic()),
                    include_comments=False,
                    max_posts=min(2, request.page_size),
                    sort=request.sort,
                )
                items = tuple(posts)
            elif isinstance(request, CommentsRequest):
                if not request.post_external_id.isascii() or not request.post_external_id.isdigit():
                    raise CollectionStoppedError("unsupported")
                _, comments, _ = collect(
                    identity_env=self._identity_env,
                    keyword="",
                    starts_at=datetime(1970, 1, 1, tzinfo=UTC),
                    ends_at=datetime.now(UTC),
                    charge=charge,
                    transport=self._transport,
                    deadline_seconds=max(0.0, self._deadline - time.monotonic()),
                    comment_post=request.post_external_id,
                )
                items = tuple(comments[: request.page_size])
            else:
                raise CollectionStoppedError("unsupported")
        except CollectionStoppedError as error:
            reason = {
                "chrome_login_required": SourceStopReason.AUTHENTICATION_REQUIRED,
                "chrome_session_unavailable": SourceStopReason.AUTHENTICATION_REQUIRED,
                "source_access_or_rate_limited": SourceStopReason.RATE_LIMITED,
                "cancelled": SourceStopReason.CANCELLED,
                "budget_exhausted": SourceStopReason.BUDGET_EXHAUSTED,
                "unsupported": SourceStopReason.UNSUPPORTED,
            }.get(str(error), SourceStopReason.PROTOCOL_ERROR)
            state = SourcePageState.STOPPED
        if state is SourcePageState.PARTIAL and not items:
            state = SourcePageState.STOPPED
        return SourcePage(
            source_key="bilibili",
            capability=request.capability,
            state=state,
            items=items,
            next_page_token=None,
            watermark=None,
            stop_reason=reason,
            observed_at=datetime.now(UTC),
            request_count=count,
            adapter_version=VERSION,
        )
