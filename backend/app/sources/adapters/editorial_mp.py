"""Bounded MP account/body protocol port; Dajiala remains explicitly unauthorized.

Provider receipts/costs are reported to injected original metering; no new paid ledger.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import Field, SecretStr

from sources.adapters.editorial_http import EditorialHttpClient, EditorialSourceError
from sources.adapters.editorial_parsing import material, sanitize_html
from sources.editorial_registry import EditorialKnownMaterial
from sources.editorial_schemas import (
    EditorialAuthorization,
    EditorialContract,
    EditorialCursor,
    EditorialMaterial,
    EditorialPage,
    EditorialSourceConfiguration,
    public_url,
)


class MpPost(EditorialContract):
    url: str = Field(max_length=2048)
    title: str = Field(min_length=1, max_length=2000)
    post_time: int = Field(ge=0)
    digest: str | None = Field(default=None, max_length=4000)
    sn: str | None = Field(default=None, max_length=512)
    cover_url: str | None = Field(default=None, max_length=2048)
    position: int = Field(default=0, ge=0, le=1000)
    original: int | None = None
    item_show_type: int | None = None


class MpHistory(EditorialContract):
    posts: tuple[MpPost, ...] = Field(default=(), max_length=1000)
    nickname: str | None = Field(default=None, max_length=128)


class MpArticle(EditorialContract):
    title: str = Field(default="", max_length=2000)
    content: str = Field(default="", max_length=500000)
    author: str | None = Field(default=None, max_length=256)
    desc: str | None = Field(default=None, max_length=4000)
    pubtime: str | None = Field(default=None, max_length=128)


class MpProvider(Protocol):
    @property
    def request_count(self) -> int: ...
    def history(self, account: str, *, window: str) -> MpHistory: ...
    def article(self, url: str, *, identity: str) -> MpArticle: ...


class DajialaEditorialClient:
    def __init__(
        self,
        http: EditorialHttpClient,
        *,
        key: SecretStr,
        report_cost: Callable[[str, Decimal | None], None],
        before_paid: Callable[[str], bool] = lambda purpose: False,
        base_url: str = "https://www.dajiala.com",
    ) -> None:
        self._before = before_paid
        self._http, self._key, self._report, self._base = (
            http,
            key,
            report_cost,
            public_url(base_url).rstrip("/"),
        )

    @property
    def request_count(self) -> int:
        return self._http.request_count

    def history(self, account: str, *, window: str) -> MpHistory:
        if not account or len(account) > 128 or len(window) > 128:
            raise EditorialSourceError("source_protocol_error")
        obj = self._get(
            self._base + "/fbmain/monitor/v3/post_history",
            purpose="mp_history",
            body={"ghid": account, "key": self._key.get_secret_value(), "verifycode": ""},
        )
        try:
            return MpHistory(
                posts=tuple(MpPost.model_validate(p) for p in obj.get("data", [])),
                nickname=obj.get("nickname"),
            )
        except (ValueError, TypeError, AttributeError):
            raise EditorialSourceError("source_protocol_error") from None

    def article(self, url: str, *, identity: str) -> MpArticle:
        url = public_url(url)
        if len(identity) > 512:
            raise EditorialSourceError("source_protocol_error")
        obj = self._get(
            self._base
            + "/fbmain/monitor/v3/article_detail?"
            + urlencode({"url": url, "mode": "1", "verifycode": ""}),
            purpose="mp_article",
        )
        try:
            return MpArticle.model_validate(
                {key: obj[key] for key in MpArticle.model_fields if key in obj}
            )
        except (ValueError, TypeError):
            raise EditorialSourceError("source_protocol_error") from None

    def _get(self, url: str, *, purpose: str, body: dict[str, str] | None = None) -> dict[str, Any]:
        if not self._before(purpose):
            raise EditorialSourceError("budget_exhausted", blocked=True)
        previous_requests = self._http.request_count
        try:
            response = self._http.request(
                url,
                method="POST" if body else "GET",
                headers={"content-type": "application/json", "accept": "application/json"},
                body=json.dumps(body).encode() if body else None,
                same_origin_redirects=True,
                credential_query=None if body else {"key": self._key},
            )
            obj = json.loads(response.text)
            if not isinstance(obj, dict) or not isinstance(obj.get("code"), int):
                raise ValueError
            code = obj["code"]
            if code != 0:
                self._report(purpose, None)
                raise EditorialSourceError(
                    "rate_limited"
                    if code == -1
                    else "provider_balance_unavailable"
                    if code == 20001
                    else "mp_account_unavailable"
                    if code in {101, 104, 107}
                    else "provider_rejected",
                    blocked=True,
                )
            cost = (
                Decimal(str(obj["cost_money"]))
                if isinstance(obj.get("cost_money"), (float, int, str))
                else None
            )
            if cost is not None and (not cost.is_finite() or cost < 0):
                raise ValueError
            self._report(purpose, cost)
            return obj
        except EditorialSourceError:
            self._report(
                purpose, Decimal(0) if self._http.request_count == previous_requests else None
            )
            raise
        except (ValueError, TypeError):
            self._report(purpose, None)
            raise EditorialSourceError("source_protocol_error") from None


def mp_identity_url(url: str) -> str:
    normalized = public_url(url)
    p = urlsplit(normalized)
    if p.hostname == "mp.weixin.qq.com":
        query = urlencode(
            sorted(
                (key, value)
                for key, value in parse_qsl(p.query)
                if key in {"__biz", "mid", "idx", "sn"}
            )
        )
        return urlunsplit((*p[:3], query, ""))
    return normalized


class EditorialMpCollector:
    def __init__(
        self,
        provider: MpProvider | None = None,
        *,
        authorization: EditorialAuthorization | None = None,
    ) -> None:
        self._provider, self._authorization = provider, authorization or EditorialAuthorization()

    def collect(
        self,
        configuration: EditorialSourceConfiguration,
        cursor: EditorialCursor,
        known: Mapping[str, EditorialKnownMaterial],
        now: datetime,
    ) -> EditorialPage:
        if self._provider is None or not self._authorization.allowed:
            return EditorialPage(
                status="blocked",
                reason="source_authorization_required",
                cursor=cursor,
                observed_at=now,
            )
        if cursor.last_checked_at is not None and now - cursor.last_checked_at < timedelta(
            minutes=10
        ):
            return EditorialPage(
                status="blocked", reason="mp_receipt_window", cursor=cursor, observed_at=now
            )
        rows: list[EditorialMaterial] = []
        initial = cursor.last_checked_at is None
        partial = False
        try:
            history = self._provider.history(
                configuration.ghid or configuration.wxid or "",
                window=f"source:{int(now.timestamp()) // 600}",
            )
            posts = sorted(history.posts, key=lambda p: p.post_time, reverse=True)
            for p in posts:
                url = mp_identity_url(p.url)
                base = material(url, p.title)
                existing = known.get(base.identity_key)
                published = datetime.fromtimestamp(p.post_time, UTC) if p.post_time else None
                if initial and published and now - published > timedelta(days=7):
                    continue
                if existing is not None and (
                    existing.next_body_retry_at is None
                    or existing.body_status != "none"
                    or existing.body_retry_count >= 3
                    or now - existing.created_at >= timedelta(days=3)
                    or (existing.next_body_retry_at and now < existing.next_body_retry_at)
                ):
                    continue
                if len(rows) >= 8:
                    break
                article = None
                passing = False
                try:
                    article = self._provider.article(url, identity=p.sn or url)
                except EditorialSourceError as error:
                    if error.unknown:
                        raise
                    if error.code == "budget_exhausted":
                        raise
                    passing = error.code in {
                        "rate_limited",
                        "upstream_failed",
                        "target_unavailable",
                    }
                    partial = True
                html, body = (
                    sanitize_html(article.content, url)
                    if article and article.content
                    else (None, None)
                )
                retries = (existing.body_retry_count if existing else 0) + 1 if passing else 0
                rows.append(
                    material(
                        url,
                        p.title,
                        author=article.author if article else None,
                        language="zh",
                        published_at=published,
                        excerpt=p.digest or (article.desc if article else None),
                        body_text=body,
                        body_html=html,
                        body_status="ok" if body else "none",
                        media=(public_url(p.cover_url),) if p.cover_url else (),
                        metadata={
                            "content_format": "text",
                            "position": p.position,
                            "original": p.original,
                            "body_retry": min(3, retries),
                        },
                    )
                )
            updated = cursor.model_copy(
                update={
                    "initialized_at": cursor.initialized_at or now,
                    "last_checked_at": now,
                    "last_post_time": datetime.fromtimestamp(posts[0].post_time, UTC)
                    if posts and posts[0].post_time
                    else cursor.last_post_time,
                    "last_ok_at": cursor.last_ok_at if partial else now,
                }
            )
            return EditorialPage(
                status="partial" if partial else "complete",
                reason="mp_body_pending" if partial else None,
                materials=tuple(rows),
                cursor=updated,
                observed_at=now,
                request_count=self._provider.request_count,
            )
        except EditorialSourceError as error:
            return EditorialPage(
                status="unknown" if error.unknown else "blocked" if error.blocked else "partial",
                reason=error.code,
                materials=tuple(rows),
                cursor=cursor,
                observed_at=now,
                request_count=self._provider.request_count,
            )
        except (ValueError, OverflowError, OSError):
            return EditorialPage(
                status="partial",
                reason="source_protocol_error",
                materials=tuple(rows),
                cursor=cursor,
                observed_at=now,
                request_count=self._provider.request_count,
            )
