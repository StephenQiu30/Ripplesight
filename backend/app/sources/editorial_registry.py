"""Six editable collectors composed through explicit, admitted provider boundaries.

Ports AIHOT collection semantics at commit 035f7b7f (MIT; THIRD_PARTY_NOTICES).
No model, database, credential discovery, or default network admission is performed here.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Protocol

from sources.adapters.editorial_http import EditorialHttpClient, EditorialSourceError
from sources.adapters.editorial_jina import EditorialJinaReader
from sources.adapters.editorial_json import parse_json_list
from sources.adapters.editorial_rss import parse_feed
from sources.adapters.editorial_web import allowed, parse_detail, parse_web_list
from sources.editorial_schemas import (
    EditorialCursor,
    EditorialMaterial,
    EditorialPage,
    EditorialProfileView,
    EditorialSourceConfiguration,
    RssValidator,
    fingerprint,
)


class EditorialCollector(Protocol):
    def collect(
        self,
        profile: EditorialProfileView,
        cursor: EditorialCursor,
        known: Mapping[str, EditorialKnownMaterial],
    ) -> EditorialPage: ...

    def close(self) -> None: ...


class EditorialKnownMaterial(Protocol):
    body_status: str
    body_retry_count: int
    published_at: datetime | None
    created_at: datetime
    detail_title: str | None
    next_body_retry_at: datetime | None


class KindCollector(Protocol):
    def collect(
        self,
        configuration: EditorialSourceConfiguration,
        cursor: EditorialCursor,
        known: Mapping[str, EditorialKnownMaterial],
        now: datetime,
    ) -> EditorialPage: ...


def noise_keep(item: EditorialMaterial, config: EditorialSourceConfiguration) -> bool:
    noise = config.ingest_noise_filter
    if noise is None:
        return True
    title, body = item.title.casefold(), (item.excerpt or item.body_text or "").casefold()
    if any(marker.casefold() in f"{title}\n{body}" for marker in noise.keep_if_matches):
        return True
    if any(marker.casefold() in title for marker in noise.drop_markers_title_only):
        return False
    return not any(marker.casefold() in f"{title}\n{body}" for marker in noise.drop_markers)


def filter_materials(
    items: tuple[EditorialMaterial, ...],
    config: EditorialSourceConfiguration,
    cursor: EditorialCursor,
    now: datetime,
) -> tuple[EditorialMaterial, ...]:
    unique: dict[str, EditorialMaterial] = {}
    for item in items:
        if not allowed(item.url, config) or not noise_keep(item, config):
            continue
        cats = {value.casefold() for value in item.categories}
        if cats.intersection(value.casefold() for value in config.deny_categories):
            continue
        if config.allow_categories and not cats.intersection(
            value.casefold() for value in config.allow_categories
        ):
            continue
        if config.item_url_prefix_rewrite and item.url.startswith(
            config.item_url_prefix_rewrite.from_prefix
        ):
            url = (
                config.item_url_prefix_rewrite.to_prefix
                + item.url[len(config.item_url_prefix_rewrite.from_prefix) :]
            )
            item = EditorialMaterial.model_validate(
                {
                    **item.model_dump(),
                    "url": url,
                    "identity_key": f"url:{url}"
                    if len(url) < 508
                    else f"sha256:{fingerprint(url).hex()}",
                }
            )
        unique.setdefault(item.identity_key, item)
    out = list(unique.values())
    if config.sort_by_published_at:
        out.sort(key=lambda row: row.published_at or datetime.min.replace(tzinfo=UTC), reverse=True)
    if cursor.initialized_at is None:
        cutoff = now - timedelta(days=config.initial_backfill_months * 30)
        out = [row for row in out if row.published_at is None or row.published_at >= cutoff][
            : config.initial_backfill_limit
        ]
    return tuple(out)


class EditorialSourceRegistry:
    def __init__(
        self,
        *,
        http: EditorialHttpClient | None = None,
        x: KindCollector | None = None,
        jina: EditorialJinaReader | None = None,
        mp: KindCollector | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        preview: bool = False,
        blocked_reason: str | None = None,
    ) -> None:
        self._http, self._x, self._mp, self._clock, self._jina = http, x, mp, clock, jina
        self._preview = preview
        self._blocked_reason = blocked_reason

    def collect(
        self,
        profile: EditorialProfileView,
        cursor: EditorialCursor,
        known: Mapping[str, EditorialKnownMaterial],
    ) -> EditorialPage:
        now = self._clock()
        c = profile.configuration
        if self._blocked_reason:
            return EditorialPage(
                status="blocked", reason=self._blocked_reason, cursor=cursor, observed_at=now
            )
        if not profile.enabled:
            return EditorialPage(
                status="blocked", reason="source_disabled", cursor=cursor, observed_at=now
            )
        if c.kind == "external":
            return EditorialPage(
                status="blocked", reason="external_ingest_only", cursor=cursor, observed_at=now
            )
        delegate = self._x if c.kind == "x_search" else self._mp if c.kind == "mp_account" else None
        if c.kind in {"x_search", "mp_account"}:
            if delegate is None:
                return EditorialPage(
                    status="blocked",
                    reason="source_authorization_required",
                    cursor=cursor,
                    observed_at=now,
                )
            return delegate.collect(c, cursor, known, now)
        if self._http is None:
            return EditorialPage(
                status="blocked",
                reason="source_authorization_required",
                cursor=cursor,
                observed_at=now,
            )
        try:
            if c.kind == "rss":
                rows, next_cursor, unchanged = self._rss(c, cursor)
            elif c.kind == "json_list":
                response = self._http.request(
                    c.url or "",
                    method=c.method,
                    headers=c.headers,
                    body=json.dumps(c.body_json, allow_nan=False).encode()
                    if c.method == "POST"
                    else None,
                    same_origin_redirects=True,
                )
                rows = parse_json_list(response.text, c)
                next_cursor, unchanged = cursor, False
            else:
                http = self._http
                if (c.url or "").startswith("https://r.jina.ai/"):
                    if self._jina is None:
                        raise EditorialSourceError("source_authorization_required", blocked=True)
                    response = self._jina.read(
                        c.url or "",
                        format="markdown" if c.parse_mode == "markdown" else "html",
                        cache_tolerance=c.cache_tolerance_seconds,
                    )
                else:
                    response = http.request(c.url or "")
                rows = parse_web_list(
                    response.text,
                    response.url,
                    c,
                    script_fetcher=lambda url: http.request(url).text,
                )
                next_cursor, unchanged = cursor, False
            rows = filter_materials(rows, c, cursor, now)
            if not self._preview:
                rows = self._details(rows, c, known)
            updated = next_cursor.model_copy(
                update={"initialized_at": cursor.initialized_at or now, "last_ok_at": now}
            )
            return EditorialPage(
                status="unchanged" if unchanged else "complete",
                materials=rows,
                cursor=updated,
                request_count=self._http.request_count,
                observed_at=now,
            )
        except EditorialSourceError as error:
            return EditorialPage(
                status="unknown" if error.unknown else "blocked" if error.blocked else "partial",
                reason=error.code,
                cursor=cursor,
                request_count=self._http.request_count,
                observed_at=now,
            )
        except (ValueError, UnicodeError, KeyError, IndexError):
            return EditorialPage(
                status="partial",
                reason="source_protocol_error",
                cursor=cursor,
                request_count=self._http.request_count,
                observed_at=now,
            )

    def close(self) -> None:
        if self._http is not None:
            self._http.close()

    def _rss(
        self, c: EditorialSourceConfiguration, cursor: EditorialCursor
    ) -> tuple[tuple[EditorialMaterial, ...], EditorialCursor, bool]:
        assert self._http is not None
        digest = fingerprint(c.model_dump(mode="json")).hex()
        validator = cursor.rss
        headers = {}
        if validator and cursor.initialized_at and validator.configuration_hash == digest:
            if validator.etag:
                headers["if-none-match"] = validator.etag
            if validator.last_modified:
                headers["if-modified-since"] = validator.last_modified
        response = self._http.request(
            c.feed_url or "", headers=headers, accepted_statuses=frozenset({200, 304})
        )
        if response.status == 304 and (
            not headers or not validator or response.url != validator.response_url
        ):
            if c.rsshub is not None:
                raise EditorialSourceError("rsshub_unexpected_not_modified")
            response = self._http.request(c.feed_url or "")
        if response.status == 304:
            return (), cursor, True
        rows = parse_feed(response.text, response.url, c)
        updated = cursor.model_copy(
            update={
                "rss": RssValidator(
                    configuration_hash=digest,
                    response_url=response.url,
                    etag=response.headers.get("etag"),
                    last_modified=response.headers.get("last-modified"),
                )
            }
        )
        return rows, updated, False

    def _details(
        self,
        rows: tuple[EditorialMaterial, ...],
        c: EditorialSourceConfiguration,
        known: Mapping[str, EditorialKnownMaterial],
    ) -> tuple[EditorialMaterial, ...]:
        if self._http is None or c.detail is None or c.detail.max_fetches == 0:
            return rows
        out = []
        fetched = 0
        for row in rows:
            previous = known.get(row.identity_key)
            if previous is not None:
                if previous.detail_title:
                    row = row.model_copy(update={"title": previous.detail_title})
                out.append(row)
                continue
            if fetched >= c.detail.max_fetches:
                out.append(row)
                continue
            fetched += 1
            response = self._http.request(row.url)
            values = parse_detail(response.text, response.url, c)
            values = {
                key: value
                for key, value in values.items()
                if value is not None
                or (key == "published_at" and c.detail.published_at_authoritative)
            }
            detail_title = values.pop("title", None)
            if isinstance(detail_title, str) and (
                c.detail.title_authoritative
                or len(row.title) > 100
                or "read more" in row.title.casefold()
            ):
                values["title"] = detail_title
                values["metadata"] = {**row.metadata, "detail_title": detail_title}
            date = values.get("published_at")
            if (
                isinstance(date, datetime)
                and row.published_at
                and c.detail.upgrade_date_precision
                and (
                    row.published_at.date() != date.date()
                    or abs((row.published_at - date).total_seconds()) >= 86400
                )
            ):
                values.pop("published_at", None)
            out.append(EditorialMaterial.model_validate({**row.model_dump(), **values}))
        return tuple(out)
