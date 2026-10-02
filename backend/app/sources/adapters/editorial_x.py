"""Official X v2 search/lookup only; no SocialData URL or fallback requests.

Current reference: https://docs.x.com/x-api/posts/search-recent-posts .
Both current post and former tweet response names are parsed; wire dialect is explicit.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal
from urllib.parse import urlencode
from uuid import UUID

from pydantic import SecretStr

from sources.adapters.editorial_http import EditorialHttpClient, EditorialSourceError
from sources.adapters.editorial_parsing import material, parse_loose_date
from sources.editorial_registry import EditorialKnownMaterial, filter_materials
from sources.editorial_schemas import (
    EditorialCursor,
    EditorialMaterial,
    EditorialPage,
    EditorialProfileView,
    EditorialSourceConfiguration,
    EditorialSourceMedia,
    SearchBacklog,
    fingerprint,
    public_url,
)


@dataclass(frozen=True)
class OfficialXPage:
    materials: tuple[EditorialMaterial, ...]
    next_token: str | None
    posts: tuple[dict[str, Any], ...]
    billed_author_handles: tuple[str | None, ...] = ()


class OfficialEditorialXClient:
    def __init__(
        self,
        http: EditorialHttpClient,
        *,
        bearer: SecretStr,
        dialect: Literal["post", "tweet"] = "post",
        report_posts: Callable[[int | None], None] = lambda count: None,
    ) -> None:
        self._http, self._bearer, self._dialect = http, bearer, dialect
        self._report_posts = report_posts

    @property
    def request_count(self) -> int:
        return self._http.request_count

    def _params(self) -> dict[str, str]:
        return {
            f"{self._dialect}.fields": (
                "id,text,created_at,author_id,referenced_posts,lang,public_metrics,article,note_post"
            )
            if self._dialect == "post"
            else "id,text,created_at,author_id,lang,public_metrics,referenced_tweets,note_tweet",
            "expansions": "author_id,referenced_posts,attachments.media_keys"
            if self._dialect == "post"
            else (
                "author_id,referenced_tweets.id,referenced_tweets.id.author_id,att"
                "achments.media_keys"
            ),
            "user.fields": "id,username,name,profile_image_url",
            "media.fields": "url,preview_image_url,type,variants,alt_text",
        }

    def search(
        self,
        query: str,
        *,
        since_id: str | None = None,
        next_token: str | None = None,
        top: bool = False,
        starts_at: datetime | None = None,
        ends_at: datetime | None = None,
    ) -> OfficialXPage:
        if (
            not query.strip()
            or len(query) > 1024
            or (since_id is not None and not re.fullmatch(r"[0-9]{1,19}", since_id))
            or (next_token is not None and len(next_token) > 4096)
        ):
            raise EditorialSourceError("source_protocol_error")
        # Convert only the known AIHOT reply-exclusion spelling to official syntax.
        query = query.replace("-filter:replies", "-is:reply")
        params = {
            **self._params(),
            "query": query,
            "max_results": "100",
            "sort_order": "relevancy" if top else "recency",
        }
        if since_id:
            params["since_id"] = since_id
        if next_token:
            params["next_token"] = next_token
        if starts_at is not None:
            params["start_time"] = starts_at.isoformat(timespec="seconds").replace("+00:00", "Z")
        if ends_at is not None:
            params["end_time"] = ends_at.isoformat(timespec="seconds").replace("+00:00", "Z")
        return self._get("https://api.x.com/2/tweets/search/recent?" + urlencode(params))

    def lookup(self, post_id: str) -> OfficialXPage:
        if not re.fullmatch(r"[0-9]{1,19}", post_id):
            raise EditorialSourceError("source_protocol_error")
        return self._get(f"https://api.x.com/2/tweets/{post_id}?" + urlencode(self._params()))

    def _get(self, url: str) -> OfficialXPage:
        response = self._http.request(
            url,
            headers={"authorization": "Bearer " + self._bearer.get_secret_value()},
            same_origin_redirects=True,
        )
        try:
            obj = json.loads(response.text)
            if not isinstance(obj, dict):
                raise ValueError
            if obj.get("errors") and not obj.get("data"):
                raise ValueError
            rows = obj.get("data", [])
            if isinstance(rows, dict):
                rows = [rows]
            if not isinstance(rows, list) or len(rows) > 100:
                raise ValueError
            included = obj.get("includes", {})
            if not isinstance(included, dict):
                raise ValueError
            users = {
                str(u["id"]): u
                for u in included.get("users", [])
                if isinstance(u, dict) and "id" in u
            }
            media = {
                str(m["media_key"]): m
                for m in included.get("media", [])
                if isinstance(m, dict) and "media_key" in m
            }
            materials = []
            posts = []
            billed_authors: list[str | None] = []
            for row in rows:
                if not isinstance(row, dict) or not re.fullmatch(
                    r"[0-9]{1,19}", str(row.get("id", ""))
                ):
                    raise ValueError
                posts.append(row)
                user = users.get(str(row.get("author_id")), {})
                handle = user.get("username")
                valid_handle = (
                    handle
                    if isinstance(handle, str) and re.fullmatch(r"[A-Za-z0-9_]{1,15}", handle)
                    else None
                )
                billed_authors.append(valid_handle)
                refs = row.get("referenced_posts", row.get("referenced_tweets", []))
                if not isinstance(refs, list):
                    raise ValueError
                if any(
                    ref.get("type") in {"retweeted", "reposted"}
                    for ref in refs
                    if isinstance(ref, dict)
                ):
                    continue
                handle = valid_handle or "i"
                note = row.get("note_post", row.get("note_tweet", {}))
                note_text = note.get("text") if isinstance(note, dict) else None
                body = note_text if isinstance(note_text, str) and note_text else row.get("text")
                if not isinstance(body, str) or not body or len(body) > 100000:
                    raise ValueError
                images: list[str] = []
                media_details = []
                attachments = row.get("attachments", {})
                for key in (
                    attachments.get("media_keys", []) if isinstance(attachments, dict) else []
                ):
                    item = media.get(key, {})
                    variants = item.get("variants", [])
                    playable = (
                        [
                            v
                            for v in variants
                            if isinstance(v, dict)
                            and v.get("content_type") == "video/mp4"
                            and isinstance(v.get("url"), str)
                        ]
                        if isinstance(variants, list)
                        else []
                    )
                    playable.sort(
                        key=lambda v: (
                            v.get("bit_rate", 0) if isinstance(v.get("bit_rate"), int) else 0
                        ),
                        reverse=True,
                    )
                    candidates = []
                    if item.get("type") in ("video", "animated_gif") and playable:
                        candidates.append((playable[0]["url"], "video"))
                    if isinstance(item.get("url"), str):
                        candidates.append(
                            (item["url"], "image" if item.get("type") == "photo" else "unknown")
                        )
                    if isinstance(item.get("preview_image_url"), str):
                        candidates.append((item["preview_image_url"], "image"))
                    for image, media_kind in candidates:
                        try:
                            normalized = public_url(image)
                            if normalized not in images and len(images) < 6:
                                images.append(normalized)
                                media_details.append(
                                    EditorialSourceMedia(
                                        url=normalized,
                                        kind=media_kind,
                                        alt=item.get("alt_text")
                                        if isinstance(item.get("alt_text"), str)
                                        else None,
                                    )
                                )
                        except ValueError:
                            continue
                article = row.get("article")
                pending = bool(article) and not note_text
                meta: dict[str, Any] = {
                    "content_format": "text",
                    "author_external_id": str(row.get("author_id") or ""),
                    "author_handle": handle,
                    "references": [
                        {"id": str(ref.get("id")), "type": str(ref.get("type"))}
                        for ref in refs
                        if isinstance(ref, dict)
                    ],
                }
                avatar_url = user.get("profile_image_url")
                if isinstance(avatar_url, str):
                    with suppress(ValueError):
                        meta["avatar_url"] = public_url(avatar_url)
                public_metrics = row.get("public_metrics")
                if isinstance(public_metrics, dict):
                    meta["public_metrics"] = {
                        key: value
                        for key, value in public_metrics.items()
                        if isinstance(value, int) and value >= 0
                    }
                materials.append(
                    material(
                        f"https://x.com/{handle}/status/{row['id']}",
                        body.splitlines()[0][:2000],
                        identity_key=f"x:{row['id']}",
                        external_id=str(row["id"]),
                        author=user.get("name") or handle,
                        language=row.get("lang"),
                        published_at=parse_loose_date(row.get("created_at"), "+00:00"),
                        excerpt=body[:2000],
                        body_text=None if pending else body,
                        body_status="pending" if pending else "ok",
                        media=tuple(images[:6]),
                        media_details=tuple(media_details),
                        metadata=meta,
                    )
                )
            meta = obj.get("meta", {})
            token = meta.get("next_token") if isinstance(meta, dict) else None
            if token is not None and (not isinstance(token, str) or not token or len(token) > 4096):
                raise ValueError
            self._report_posts(len(rows))
            return OfficialXPage(tuple(materials), token, tuple(posts), tuple(billed_authors))
        except (ValueError, TypeError, KeyError, AttributeError) as error:
            self._report_posts(None)
            raise EditorialSourceError("source_protocol_error", unknown=True) from error


class EditorialXCollector:
    def __init__(
        self, client: OfficialEditorialXClient, *, fresh_pages: int = 10, backlog_pages: int = 10
    ) -> None:
        if not 1 <= fresh_pages <= 10 or not 1 <= backlog_pages <= 10:
            raise ValueError("X page budget exceeds migration limit")
        self._client, self._fresh, self._backlog = client, fresh_pages, backlog_pages

    def collect(
        self,
        configuration: EditorialSourceConfiguration,
        cursor: EditorialCursor,
        known: Mapping[str, EditorialKnownMaterial],
        now: datetime,
    ) -> EditorialPage:
        if any(gap.group_manifest_json is not None for gap in cursor.x_backlog):
            return EditorialPage(
                status="blocked", reason="x_group_gap_pending", cursor=cursor, observed_at=now
            )
        rows: dict[str, EditorialMaterial] = {}
        backlog = list(cursor.x_backlog)
        maximum = cursor.last_tweet_id
        initial = cursor.initialized_at is None
        query = configuration.query or ""
        top = configuration.search_type == "Top"

        def collect_pages(
            query: str, since: str | None, token: str | None, limit: int
        ) -> str | None:
            nonlocal maximum
            seen: set[str] = set()
            for _ in range(limit):
                result = self._client.search(query, since_id=since, next_token=token, top=top)
                for m in result.materials:
                    rows.setdefault(m.identity_key, m)
                    if m.external_id and (maximum is None or int(m.external_id) > int(maximum)):
                        maximum = m.external_id
                token = result.next_token
                if not token:
                    return None
                if token in seen:
                    raise EditorialSourceError("repeated_pagination_token")
                seen.add(token)
            return token

        try:
            if len(backlog) < 100:
                token = collect_pages(
                    query, cursor.last_tweet_id, None, 1 if initial else self._fresh
                )
                if token and not initial:
                    candidate = SearchBacklog(
                        query=query, next_token=token, stop_at_id=cursor.last_tweet_id
                    )
                    if not any(
                        (v.query, v.next_token, v.stop_at_id)
                        == (candidate.query, candidate.next_token, candidate.stop_at_id)
                        for v in backlog
                    ):
                        backlog.append(candidate)
            old = backlog[: len(cursor.x_backlog)]
            removed: set[int] = set()
            remaining = self._backlog
            for index, gap in enumerate(old):
                if remaining <= 0:
                    break
                if gap.state == "held":
                    continue
                try:
                    start = self._client.request_count
                    token = collect_pages(gap.query, gap.stop_at_id, gap.next_token, remaining)
                    remaining -= self._client.request_count - start
                except EditorialSourceError as error:
                    if error.unknown:
                        raise
                    if error.code in {"budget_exhausted", "rate_limited", "cancelled"}:
                        break
                    backlog[index] = gap.model_copy(
                        update={"state": "held", "failure_code": error.code}
                    )
                    continue
                if token:
                    backlog[index] = gap.model_copy(update={"next_token": token})
                else:
                    removed.add(index)
            backlog = [gap for index, gap in enumerate(backlog) if index not in removed]
            pending = bool(backlog)
            updated = cursor.model_copy(
                update={
                    "last_tweet_id": maximum,
                    "x_backlog": tuple(backlog),
                    "initialized_at": cursor.initialized_at or now,
                    "last_ok_at": cursor.last_ok_at if pending else now,
                }
            )
            return EditorialPage(
                status="partial" if pending else "complete",
                reason="x_gap_pending" if pending else None,
                materials=filter_materials(tuple(rows.values()), configuration, cursor, now),
                cursor=updated,
                observed_at=now,
                request_count=self._client.request_count,
            )
        except EditorialSourceError as error:
            return EditorialPage(
                status="unknown" if error.unknown else "blocked" if error.blocked else "partial",
                reason=error.code,
                materials=tuple(rows.values()),
                cursor=cursor,
                observed_at=now,
                request_count=self._client.request_count,
            )


@dataclass(frozen=True)
class XSearchShard:
    key: str
    query: str
    members: tuple[UUID, ...]
    handles: tuple[str, ...]
    since_id: str
    interval_minutes: int


def shard_eligible(
    profiles: tuple[EditorialProfileView, ...], cursors: Mapping[UUID, EditorialCursor]
) -> tuple[XSearchShard, ...]:
    groups: dict[str, list[tuple[EditorialProfileView, str]]] = {}
    for p in sorted(profiles, key=lambda item: str(item.id)):
        if (
            not p.enabled
            or p.configuration.kind != "x_search"
            or p.configuration.search_type != "Latest"
            or not cursors[p.id].last_tweet_id
        ):
            continue
        match = re.fullmatch(
            r"from:([A-Za-z0-9_]{1,15})(?:\s+-(?:filter:replies|is:reply))?",
            p.configuration.query or "",
            re.IGNORECASE,
        )
        if match:
            groups.setdefault(p.participation_mode, []).append((p, match[1]))
    shards = []
    for mode, items in sorted(groups.items()):
        current: list[tuple[EditorialProfileView, str]] = []

        def append(batch: list[tuple[EditorialProfileView, str]], current_mode: str = mode) -> None:
            if not batch:
                return
            members = tuple(p.id for p, _ in batch)
            covered = []
            for p, _ in batch:
                cursor = cursors[p.id]
                bound = int(cursor.last_tweet_id or "0")
                if cursor.last_ok_at:
                    milliseconds = int(
                        (cursor.last_ok_at - timedelta(minutes=10)).timestamp() * 1000
                    )
                    bound = max(bound, max(0, milliseconds - 1288834974657) << 22)
                covered.append(bound)
            shards.append(
                XSearchShard(
                    f"x-shard:{fingerprint([str(i) for i in members]).hex()[:32]}",
                    "(" + " OR ".join(f"from:{handle}" for _, handle in batch) + ") -is:reply",
                    members,
                    tuple(handle for _, handle in batch),
                    str(min(covered)),
                    60 if current_mode == "hot_signal" else 30,
                )
            )

        for item in items:
            candidate = [*current, item]
            query = "(" + " OR ".join(f"from:{handle}" for _, handle in candidate) + ") -is:reply"
            if len(candidate) > 24 or len(query) > 470:
                append(current)
                current = [item]
            else:
                current = candidate
        append(current)
    return tuple(shards)
