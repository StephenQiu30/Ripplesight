"""Bounded official group pages with author allocation and original member cursors."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from uuid import UUID

from jobs.editorial_schemas import EditorialGroupManifest
from sources.adapters.editorial_http import EditorialSourceError
from sources.adapters.editorial_x import OfficialEditorialXClient
from sources.editorial_registry import EditorialKnownMaterial, filter_materials
from sources.editorial_schemas import (
    EditorialCursor,
    EditorialMaterial,
    EditorialPage,
    EditorialProfileView,
    SearchBacklog,
)

type GroupInputs = Mapping[
    UUID, tuple[EditorialProfileView, EditorialCursor, Mapping[str, EditorialKnownMaterial]]
]
type GroupCost = Callable[[int | None, Mapping[str, int] | None], None]


def collect_editorial_group(
    manifest: EditorialGroupManifest,
    inputs: GroupInputs,
    client: OfficialEditorialXClient,
    *,
    now: datetime,
    report_cost: GroupCost,
    fresh_pages: int = 10,
    backlog_pages: int = 10,
) -> dict[UUID, EditorialPage]:
    if not 1 <= fresh_pages <= 10 or not 1 <= backlog_pages <= 10:
        raise ValueError("group page counts exceed original migration limits")
    if set(inputs) != {m.profile_id for m in manifest.members}:
        raise ValueError("every group member needs its own input")
    by_author = {m.handle.casefold(): m for m in manifest.members}
    materials: dict[UUID, dict[str, EditorialMaterial]] = {
        m.profile_id: {} for m in manifest.members
    }
    maximum = {i: cursor.last_tweet_id for i, (_, cursor, _) in inputs.items()}
    gaps: list[SearchBacklog] = []
    for _, cursor, _ in inputs.values():
        for gap in cursor.x_backlog:
            if gap.group_manifest_json is None:
                raise ValueError("individual query backlog cannot borrow a group HTTP")
            frozen = EditorialGroupManifest.model_validate_json(gap.group_manifest_json)
            if frozen.query != manifest.query or {m.profile_id for m in frozen.members} != {
                m.profile_id for m in manifest.members
            }:
                raise ValueError("backlog must keep its original query and members")
            if not any(
                (g.query, g.next_token, g.stop_at_id) == (gap.query, gap.next_token, gap.stop_at_id)
                for g in gaps
            ):
                gaps.append(gap)
    reason = None
    unknown = False
    request_start = client.request_count
    next_fresh = None
    request_cost_open = False
    old_gaps = list(gaps)

    def page(query: str, since: str | None, token: str | None) -> str | None:
        nonlocal request_cost_open
        request_cost_open = True
        answer = client.search(query, since_id=since, next_token=token)
        counts = {m.source_key: 0 for m in manifest.members}
        if len(answer.billed_author_handles) != len(answer.posts):
            raise EditorialSourceError("group_author_unavailable", unknown=True)
        for raw, author in zip(answer.posts, answer.billed_author_handles, strict=True):
            member = by_author.get(author.casefold()) if author else None
            if member is None:
                raise EditorialSourceError("group_author_unavailable", unknown=True)
            counts[member.source_key] += 1
            ident = str(raw["id"])
            old = maximum[member.profile_id]
            if old is None or int(ident) > int(old):
                maximum[member.profile_id] = ident
        report_cost(len(answer.posts), counts)
        request_cost_open = False
        for material in answer.materials:
            handle = material.metadata.get("author_handle")
            member = by_author.get(handle.casefold()) if isinstance(handle, str) else None
            if member is None:
                raise EditorialSourceError("group_author_unavailable", unknown=True)
            materials[member.profile_id].setdefault(material.identity_key, material)
        return answer.next_token

    try:
        seen = set()
        for _ in range(fresh_pages):
            next_fresh = page(manifest.query, manifest.since_id, next_fresh)
            if not next_fresh:
                break
            if next_fresh in seen:
                raise EditorialSourceError("repeated_pagination_token", unknown=True)
            seen.add(next_fresh)
        if next_fresh:
            candidate = SearchBacklog(
                query=manifest.query,
                next_token=next_fresh,
                stop_at_id=manifest.since_id,
                group_manifest_json=manifest.model_dump_json(),
            )
            if not any(
                (g.query, g.next_token, g.stop_at_id)
                == (candidate.query, candidate.next_token, candidate.stop_at_id)
                for g in gaps
            ):
                gaps.append(candidate)
        remaining = backlog_pages
        for gap in old_gaps:
            if remaining <= 0 or gap.state == "held":
                continue
            token: str | None = gap.next_token
            seen = set()
            while token and remaining > 0:
                remaining -= 1
                token = page(gap.query, gap.stop_at_id, token)
                if token in seen:
                    raise EditorialSourceError("repeated_pagination_token", unknown=True)
                if token:
                    seen.add(token)
                index = gaps.index(gap)
                if not token:
                    gaps.pop(index)
                    break
                replacement = gap.model_copy(update={"next_token": token})
                gaps[index] = replacement
                gap = replacement
    except EditorialSourceError as error:
        reason, unknown = error.code, error.unknown
        if unknown and request_cost_open:
            report_cost(None, None)
        if next_fresh and not any(
            g.query == manifest.query and g.next_token == next_fresh for g in gaps
        ):
            gaps.append(
                SearchBacklog(
                    query=manifest.query,
                    next_token=next_fresh,
                    stop_at_id=manifest.since_id,
                    state="held" if unknown else "pending",
                    failure_code=reason,
                    group_manifest_json=manifest.model_dump_json(),
                )
            )
    if len(gaps) > 100:
        raise EditorialSourceError("group_backlog_limit", unknown=True)
    result = {}
    for member in manifest.members:
        profile, cursor, _known = inputs[member.profile_id]
        selected = filter_materials(
            tuple(materials[member.profile_id].values()), profile.configuration, cursor, now
        )
        complete = not gaps and reason is None
        status = (
            "unknown"
            if unknown
            else "complete"
            if complete
            else "partial"
            if selected or gaps
            else "blocked"
        )
        next_cursor = (
            cursor
            if unknown
            else cursor.model_copy(
                update={
                    "last_tweet_id": maximum[member.profile_id],
                    "x_backlog": tuple(gaps),
                    "last_ok_at": now if complete else cursor.last_ok_at,
                }
            )
        )
        result[member.profile_id] = EditorialPage(
            status=status,
            materials=selected,
            cursor=next_cursor,
            reason=reason or ("x_group_gap_pending" if gaps else None),
            request_count=client.request_count - request_start,
            observed_at=now,
        )
    return result
