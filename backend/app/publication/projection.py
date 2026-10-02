"""Pure derivation from frozen editorial evidence and explicit publication grants."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import datetime
from typing import Any, cast

from analysis.editorial_schemas import EditorialPublicationInputView
from events.fact_schemas import EventPublicationGrouping
from publication.rules import (
    body_mode_of,
    display_tags,
    is_indexable,
    is_pool_eligible,
    is_selectable,
    may_redistribute,
    release_times,
)
from publication.schemas import ProjectionView, SourcePolicyView, Visibility


def fingerprint(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str
        ).encode()
    ).hexdigest()


def derive_projection(
    snapshot: EditorialPublicationInputView,
    policy: SourcePolicyView,
    *,
    now: datetime,
    previous: ProjectionView | None = None,
    override: dict[str, Any] | None = None,
    grouping: EventPublicationGrouping | None = None,
    released_at: datetime | None = None,
    indexing_enabled: bool = False,
) -> ProjectionView:
    material, source, run = snapshot.material, snapshot.source, snapshot.run
    result = run.result
    if result is None or run.status != "complete":
        raise ValueError("publication requires completed editorial evidence")
    manual = override or {}
    writing = result.writing
    title = writing.title_zh.strip() if writing else material.title.strip()
    summary = writing.summary_zh.strip() if writing and writing.summary_zh.strip() else None
    eligible = is_pool_eligible(policy.participation_mode, result.relevance, title, summary)
    selected = is_selectable(eligible, result.selected, source.tier)
    visibility = cast(
        Visibility,
        "withdrawn"
        if policy.participation_mode == "isolated"
        else manual.get("visibility", "public"),
    )
    body_mode = body_mode_of(
        policy.site_fulltext,
        material.body_complete and not material.body_pending,
        bool(material.body),
    )
    ready, visible = release_times(
        selected,
        now=now,
        delay_seconds=policy.release_delay_seconds,
        ready_at=previous.selected_ready_at if previous else None,
        visible_after=previous.visible_after if previous else None,
        grouped_at=grouping.grouped_at if grouping else None,
        released_at=released_at,
    )
    tags = display_tags(
        result.tags_override
        if result.tags_override is not None
        else result.structure.tags
        if result.structure
        else writing.tags or []
        if writing
        else []
    )
    digest = fingerprint(
        {
            "run": run.model_dump(mode="json"),
            "material": material.model_dump(mode="json"),
            "source": source.model_dump(mode="json"),
            "policy": policy.model_dump(mode="json"),
            "grouping": asdict(grouping) if grouping else None,
            "override": manual,
            "timeline": snapshot.timeline_at,
            "backfill": snapshot.backfill,
            "indexing_enabled": indexing_enabled,
        }
    )
    return ProjectionView(
        content_id=material.content_id,
        content_version_id=material.content_version_id,
        editorial_run_id=run.id,
        manual_version=run.manual_version,
        source_profile_revision=source.revision,
        policy_revision=policy.revision,
        publication_revision=previous.publication_revision if previous else 1,
        event_id=grouping.event_id if grouping else None,
        event_revision=grouping.event_revision if grouping else None,
        fact_id=grouping.fact_id if grouping else None,
        root_fact_id=grouping.root_fact_id if grouping else None,
        fact_revision=grouping.fact_revision if grouping else None,
        topic_id=grouping.topic_id if grouping else None,
        source_key=material.source_key,
        source_name=source.name,
        source_kind=source.source_kind,
        first_party=source.first_party,
        visibility=visibility,
        eligible=eligible,
        selected=selected,
        silent=result.silent,
        title=title,
        original_title=material.title.strip() if material.title.strip() != title else None,
        summary=summary,
        reason=writing.reason_zh if selected and writing else None,
        category=result.structure.category if result.structure else None,
        tags=tags,
        score=result.score,
        channel="x" if source.source_kind == "x_search" else "news",
        url=material.url,
        published_at=material.published_at,
        discovered_at=snapshot.first_received_at,
        timeline_at=snapshot.timeline_at,
        sort_at=snapshot.timeline_at,
        backfill=snapshot.backfill,
        selected_ready_at=ready,
        visible_after=visible,
        body_mode=body_mode,
        syndicate=may_redistribute(policy.syndicate_fulltext, body_mode),
        indexable=is_indexable(
            visibility,
            bool(summary),
            selected,
            bool(manual.get("seo_indexed")),
            bool(manual.get("seo_excluded")),
            indexing_enabled and policy.indexable,
        ),
        input_fingerprint=digest,
    )
