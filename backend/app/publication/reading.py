"""Every output rereads current rights and the exact stored version, without publishing."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from typing import Literal
from urllib.parse import quote
from uuid import UUID

from sqlalchemy import DateTime, and_, func, or_, select
from sqlalchemy.orm import Session

from analysis.editorial_reading import load_editorial_publication_inputs_in_transaction
from analysis.editorial_schemas import EditorialPublicationInputView
from content.editorial_rendered import read_editorial_rendered_in_transaction
from core.errors import ApplicationError
from events.facts import load_publication_groupings_in_transaction
from publication.cursors import decode_cursor, encode_cursor
from publication.exports import safe_link
from publication.media import body_presentation
from publication.projection import derive_projection
from publication.publication_models import (
    PublicationRecord,
    PublicationSelectedChange,
    PublicationSourcePolicy,
    PublicationSyncState,
)
from publication.rules import has_item_page
from publication.schemas import (
    Category,
    FrozenPublicationReference,
    FullTextGrantView,
    ProjectionView,
    PublicationValidationView,
    PublicBodyView,
    PublicItemDetailView,
    PublicItemsPage,
    PublicItemView,
    PublicMediaView,
    PublicQuotedPostView,
    PublicRelatedStoryView,
    PublicSourceStatusView,
    PublicSourceView,
    ReportPublicationCandidate,
    SelectedChangesPage,
    SelectedChangeView,
    SelectedSnapshotView,
)
from publication.services import policy_view, require_transaction


def frozen_reference(projection: ProjectionView) -> FrozenPublicationReference:
    return FrozenPublicationReference.model_validate(projection.model_dump())


def editorial_subject_tags(snapshot: EditorialPublicationInputView) -> tuple[str, ...]:
    result = snapshot.run.result if snapshot.run else None
    tags = (
        result.structure.tags
        if result and result.structure
        else result.writing.tags
        if result and result.writing
        else []
    )
    subjects = result.structure.subjects if result and result.structure else []
    return tuple(
        dict.fromkeys(
            [
                *(tag for tag in tags or [] if not tag.startswith("entity:")),
                *(f"entity:{subject}" for subject in subjects),
            ]
        )
    )


def public_item(projection: ProjectionView, *, icon_url: str | None = None) -> PublicItemView:
    minimal = projection.visibility == "summary-only"
    return PublicItemView(
        id=projection.content_id,
        analysis_state=projection.analysis_state,
        summary_origin=projection.summary_origin,
        backfill=projection.backfill,
        revision=projection.publication_revision,
        title=projection.title,
        original_title=projection.original_title,
        summary=projection.summary,
        source=PublicSourceView(
            key=projection.source_key,
            name=projection.source_name,
            kind=projection.source_kind,
            first_party=projection.first_party,
            icon_url=icon_url
            or f"/api/site/source-icons/{quote(projection.source_key, safe='')}.svg",
        ),
        original_url=safe_link(projection.url),
        reading_url=f"/items/{projection.content_id}",
        published_at=projection.published_at,
        discovered_at=projection.discovered_at,
        timeline_at=projection.timeline_at,
        category=projection.category,
        tags=[] if minimal else projection.tags,
        score=projection.score,
        selected=projection.selected,
        reason=None if minimal else projection.reason,
        event_id=None if minimal else projection.event_id,
        fact_id=None if minimal else projection.fact_id,
        indexable=False if minimal else projection.indexable,
    )


def _fixed_body_in_transaction(
    session: Session, *, owner_id: UUID, snapshot: EditorialPublicationInputView, now: datetime
) -> tuple[str, Literal["text", "html", "markdown"], str, list[PublicMediaView]]:
    rendered = read_editorial_rendered_in_transaction(
        session,
        owner_id=owner_id,
        content_id=snapshot.material.content_id,
        content_version_id=snapshot.material.content_version_id,
        now=now,
    )
    if rendered is not None:
        return (
            rendered.body,
            rendered.body_format,
            rendered.sha256,
            [
                PublicMediaView(
                    key=hashlib.sha256(item.url.encode()).hexdigest()[:24],
                    kind=item.kind,
                    original_url=item.url,
                    alt=item.alt
                    or {"image": "图片", "video": "视频", "audio": "音频", "unknown": "附件"}[
                        item.kind
                    ],
                    reading_url=None,
                    state="original_link",
                )
                for item in rendered.media
            ],
        )
    body = snapshot.material.body
    return body, "text", hashlib.sha256(("text\0" + body).encode()).hexdigest(), []


class PublicationReadingService:
    def __init__(self, session: Session, *, indexing_enabled: bool = False) -> None:
        self.session, self.indexing_enabled = session, indexing_enabled
        self._source_icons: dict[str, str] = {}

    def source_icon_url(self, source_key: str) -> str | None:
        return self._source_icons.get(source_key)

    def source_status_in_transaction(self, *, owner_id: UUID) -> list[PublicSourceStatusView]:
        from connections.editorial_services import list_editorial_source_health_in_transaction

        require_transaction(self.session)
        policies = {
            row.source_key
            for row in self.session.scalars(
                select(PublicationSourcePolicy).where(PublicationSourcePolicy.owner_id == owner_id)
            )
            if row.configuration.get("participation_mode") == "editorial"
        }
        return [
            PublicSourceStatusView(
                source_key=source.source_key,
                name=source.name,
                enabled=source.enabled,
                health=source.health,
                last_success_at=source.last_success_at,
            )
            for source in list_editorial_source_health_in_transaction(
                self.session, owner_id=owner_id
            )
            if source.source_key in policies
        ]

    def item(self, projection: ProjectionView) -> PublicItemView:
        return public_item(projection, icon_url=self.source_icon_url(projection.source_key))

    def _live(
        self, *, owner_id: UUID, rows: list[PublicationRecord], now: datetime
    ) -> dict[UUID, tuple[ProjectionView, EditorialPublicationInputView]]:
        require_transaction(self.session)
        if len(rows) > 1000:
            raise ValueError("bounded publication read required")
        from connections.editorial_icon_services import read_source_icon_urls_in_transaction

        keys = tuple({row.source_key for row in rows})
        for offset in range(0, len(keys), 100):
            batch = keys[offset : offset + 100]
            for key in batch:
                self._source_icons.pop(key, None)
            self._source_icons.update(
                read_source_icon_urls_in_transaction(
                    self.session, owner_id=owner_id, source_keys=batch, now=now
                )
            )
        inputs = load_editorial_publication_inputs_in_transaction(
            self.session,
            owner_id=owner_id,
            content_ids=tuple(row.content_id for row in rows),
            now=now,
        )
        accepted = {}
        for row in rows:
            item = inputs.get(row.content_id)
            if item is None or row.content_version_id != item.material.content_version_id:
                continue
            run = item.run
            if row.data.get("editorial_run_id") != (str(run.id) if run else None):
                continue
            if row.data.get("manual_version") != (run.manual_version if run else 0):
                continue
            accepted[row.content_id] = item
        groupings = load_publication_groupings_in_transaction(
            self.session,
            owner_id=owner_id,
            content_versions={
                identity: item.material.content_version_id for identity, item in accepted.items()
            },
            now=now,
        )
        policies = {
            row.source_key: row
            for row in self.session.scalars(
                select(PublicationSourcePolicy).where(
                    PublicationSourcePolicy.owner_id == owner_id,
                    PublicationSourcePolicy.source_key.in_({row.source_key for row in rows}),
                )
            )
        }
        result = {}
        for row in rows:
            snapshot = accepted.get(row.content_id)
            policy = policies.get(row.source_key)
            if (
                snapshot is None
                or policy is None
                or not has_item_page(row.visibility, policy.configuration["participation_mode"])
            ):
                continue
            projection = derive_projection(
                snapshot,
                policy_view(policy),
                now=now,
                previous=ProjectionView.model_validate(row.data),
                override=row.override,
                grouping=groupings.get(row.content_id),
                indexing_enabled=self.indexing_enabled,
            )
            # Rights can shrink immediately. Increasing them requires an audited republish.
            stored = ProjectionView.model_validate(row.data)
            projection = projection.model_copy(
                update={
                    "sort_at": stored.sort_at,
                    "media_candidate_count": stored.media_candidate_count,
                    "body_mode": "full"
                    if stored.body_mode == "full" and projection.body_mode == "full"
                    else "summary",
                    "syndicate": stored.syndicate and projection.syndicate,
                    "indexable": stored.indexable and projection.indexable,
                }
            )
            if has_item_page(projection.visibility, policy.configuration["participation_mode"]):
                result[row.content_id] = (projection, snapshot)
        return result

    def projection_in_transaction(
        self, *, owner_id: UUID, content_id: UUID, now: datetime
    ) -> ProjectionView | None:
        require_transaction(self.session)
        row = self.session.get(PublicationRecord, (owner_id, content_id))
        value = self._live(owner_id=owner_id, rows=[row] if row else [], now=now).get(content_id)
        return value[0] if value else None

    def detail_in_transaction(
        self,
        *,
        owner_id: UUID,
        content_id: UUID,
        now: datetime,
        redistribute: bool = False,
        include_quote: bool = True,
    ) -> PublicItemDetailView | None:
        row = self.session.get(PublicationRecord, (owner_id, content_id))
        live = self._live(owner_id=owner_id, rows=[row] if row else [], now=now).get(content_id)
        if live is None:
            return None
        projection, snapshot = live
        policy = self.session.get(PublicationSourcePolicy, (owner_id, projection.source_key))
        assert policy is not None
        full = projection.visibility == "public" and projection.body_mode == "full"
        original, original_format, body_sha256, metadata_media = (
            _fixed_body_in_transaction(self.session, owner_id=owner_id, snapshot=snapshot, now=now)
            if full
            else ("", "text", "", [])
        )
        from publication.media_mirror_reading import load_available_media_in_transaction

        mirrored = (
            load_available_media_in_transaction(
                self.session,
                owner_id=owner_id,
                content_id=content_id,
                content_version_id=projection.content_version_id,
                policy_revision=projection.policy_revision,
                now=now,
                redistribute=redistribute,
            )
            if full
            else {}
        )
        presentation = (
            body_presentation(
                original,
                body_format=original_format,
                mirrored=mirrored,
                media=metadata_media,
            )
            if full
            else None
        )
        translated = None
        if full:
            # The translation domain validates its frozen material and current full-text grant.
            from analysis.translation_reading import translated_body_in_transaction

            translated = translated_body_in_transaction(
                self.session,
                owner_id=owner_id,
                content_id=content_id,
                content_version_id=projection.content_version_id,
                policy_revision=projection.policy_revision,
                now=now,
            )
        return PublicItemDetailView(
            **self.item(projection).model_dump(),
            reading_mode="full" if full else "summary-only",
            body=PublicBodyView(
                original=original,
                original_format=original_format,
                original_html=presentation[0],
                body_sha256=body_sha256,
                outline=presentation[1],
                media=presentation[2],
                translated=body_presentation(
                    translated.body_html,
                    body_format="html",
                    mirrored=mirrored,
                    media=metadata_media,
                )[0]
                if translated and translated.body_html
                else None,
                translation_complete=translated.complete if translated else False,
                translation_state=translated.status if translated else "not_requested",
                translation_revision=translated.revision if translated else None,
            )
            if presentation
            else None,
            site_fulltext=full,
            syndicate_fulltext=full and projection.syndicate,
            markdown_available=projection.visibility == "public" and bool(projection.summary),
            license_name=policy.configuration["license_name"],
            license_url=policy.configuration["license_url"],
            quoted_post=self._quoted_post_in_transaction(
                owner_id=owner_id, snapshot=snapshot, now=now, redistribute=redistribute
            )
            if include_quote and projection.visibility == "public"
            else None,
            related_stories=self._related_stories_in_transaction(
                owner_id=owner_id, event_id=projection.event_id, now=now
            )
            if include_quote and projection.visibility == "public"
            else [],
        )

    def _related_stories_in_transaction(
        self, *, owner_id: UUID, event_id: UUID | None, now: datetime
    ) -> list[PublicRelatedStoryView]:
        from events.consolidation import load_related_story_ids_in_transaction
        from publication.stories import public_stories_in_transaction

        if event_id is None:
            return []
        support = load_related_story_ids_in_transaction(
            self.session, owner_id=owner_id, event_id=event_id, now=now
        )
        ids = sorted(support, key=lambda identity: (-support[identity], str(identity)))
        result = []
        for offset in range(0, len(ids), 100):
            permitted = {
                item.id: item
                for item in public_stories_in_transaction(
                    self, owner_id=owner_id, event_ids=tuple(ids[offset : offset + 100]), now=now
                )
            }
            for identity in ids[offset : offset + 100]:
                story = permitted.get(identity)
                if story:
                    result.append(
                        PublicRelatedStoryView(
                            id=story.id,
                            revision=story.revision,
                            title=story.title,
                            summary=story.summary,
                            reading_url=f"/discover/stories/{story.id}",
                            supporting_reports=support[identity],
                        )
                    )
                    if len(result) == 6:
                        return result
        return result

    def _quoted_post_in_transaction(
        self,
        *,
        owner_id: UUID,
        snapshot: EditorialPublicationInputView,
        now: datetime,
        redistribute: bool,
    ) -> PublicQuotedPostView | None:
        from content.editorial_reading import frozen_editorial_content_in_transaction

        reference = snapshot.quote_reference
        if reference is None or reference.content_id == snapshot.material.content_id:
            return None
        fixed = frozen_editorial_content_in_transaction(
            self.session, owner_id=owner_id, reference=reference, now=now
        )
        if fixed is None:
            return None
        projection = self.projection_in_transaction(
            owner_id=owner_id, content_id=reference.content_id, now=now
        )
        if (
            projection is None
            or projection.content_version_id != reference.content_version_id
            or projection.visibility not in {"public", "summary-only"}
            or (
                projection.selected
                and (projection.visible_after is None or projection.visible_after > now)
            )
        ):
            return None
        detail = self.detail_in_transaction(
            owner_id=owner_id,
            content_id=reference.content_id,
            now=now,
            redistribute=redistribute,
            include_quote=False,
        )
        if detail is None:
            return None
        return PublicQuotedPostView(
            item=self.item(projection),
            author=fixed.observation.author_external_id,
            body=detail.body
            if detail.site_fulltext and (not redistribute or detail.syndicate_fulltext)
            else None,
        )

    def items_in_transaction(
        self,
        *,
        owner_id: UUID,
        now: datetime,
        window: Literal["24h", "7d"] = "24h",
        selected: bool = False,
        by: Literal["timeline", "published"] = "timeline",
        category: Category | None = None,
        channel: Literal["news", "x", "firstParty"] | None = None,
        source_key: str | None = None,
        tag: str | None = None,
        topic: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
        snapshot_sequence: int | None = None,
    ) -> PublicItemsPage:
        require_transaction(self.session)
        if now.utcoffset() is None or not 1 <= limit <= 100 or window not in {"24h", "7d"}:
            raise ApplicationError("invalid_publication_input")
        scope = {
            "owner": owner_id,
            "window": window,
            "selected": selected,
            "by": by,
            "category": category,
            "channel": channel,
            "source": source_key,
            "tag": tag,
            "topic": topic,
            "snapshot_sequence": snapshot_sequence,
        }
        snapshot = now
        after: tuple[datetime, UUID] | None = None
        if cursor:
            data = decode_cursor(cursor, scope)
            try:
                snapshot = datetime.fromisoformat(data["at"])
                after = (datetime.fromisoformat(data["sort"]), UUID(data["id"]))
                if snapshot.utcoffset() is None or after[0].utcoffset() is None or snapshot > now:
                    raise ValueError("invalid snapshot")
            except (ValueError, KeyError, TypeError) as error:
                raise ApplicationError("invalid_publication_cursor") from error
        sort_column = (
            func.coalesce(
                PublicationRecord.data["published_at"].astext.cast(DateTime(timezone=True)),
                PublicationRecord.data["discovered_at"].astext.cast(DateTime(timezone=True)),
            )
            if by == "published"
            else PublicationRecord.sort_at
            if selected
            else PublicationRecord.timeline_at
        )
        query = select(PublicationRecord, sort_column.label("reading_sort_at")).where(
            PublicationRecord.owner_id == owner_id,
            PublicationRecord.updated_at <= snapshot,
            sort_column <= snapshot,
            sort_column >= snapshot - timedelta(days=1 if window == "24h" else 7),
        )
        if source_key:
            query = query.where(PublicationRecord.source_key == source_key)
        if snapshot_sequence is not None:
            query = query.where(PublicationRecord.last_sequence <= snapshot_sequence)
        items: list[PublicItemView] = []
        from publication.topics import topic_match_tags_for_slug

        topic_tags = topic_match_tags_for_slug(topic) if topic else ()
        if topic and topic_tags is None:
            raise ApplicationError("invalid_publication_input")
        scanned = 0
        last: PublicationRecord | None = None
        more = False
        while len(items) < limit and scanned < 2000:
            pagequery = query
            if after:
                pagequery = pagequery.where(
                    or_(
                        sort_column < after[0],
                        and_(
                            sort_column == after[0],
                            PublicationRecord.content_id < after[1],
                        ),
                    )
                )
            sorted_rows = self.session.execute(
                pagequery.order_by(sort_column.desc(), PublicationRecord.content_id.desc()).limit(
                    min(100, 2000 - scanned)
                )
            ).all()
            rows = [row[0] for row in sorted_rows]
            sort_times = {row[0].content_id: row[1] for row in sorted_rows}
            if not rows:
                more = False
                break
            live = self._live(owner_id=owner_id, rows=rows, now=now)
            for row in rows:
                scanned += 1
                last = row
                after = (sort_times[row.content_id], row.content_id)
                value = live.get(row.content_id)
                if value:
                    projection = value[0]
                    subject_tags = editorial_subject_tags(value[1])
                    released = not projection.selected or (
                        projection.visible_after is not None and projection.visible_after <= now
                    )
                    if (
                        projection.visibility == "public"
                        and projection.eligible
                        and released
                        and (not selected or projection.selected)
                        and (category is None or projection.category == category)
                        and (
                            channel is None
                            or projection.channel == channel
                            or (channel == "firstParty" and projection.first_party)
                        )
                        and (tag is None or tag in subject_tags)
                        and (not topic_tags or bool(set(topic_tags).intersection(subject_tags)))
                    ):
                        items.append(self.item(projection))
                if len(items) == limit:
                    more = True
                    break
            if len(rows) < 100 and len(items) < limit:
                more = False
                break
            more = True
        next_cursor = (
            encode_cursor(
                scope,
                {
                    "at": snapshot,
                    "sort": after[0] if after else last.sort_at,
                    "id": last.content_id,
                },
            )
            if more and last
            else None
        )
        return PublicItemsPage(
            items=items,
            next_cursor=next_cursor,
            snapshot_at=snapshot,
            source_status=self.source_status_in_transaction(owner_id=owner_id),
        )

    def effective_sequence_in_transaction(
        self, *, owner_id: UUID, now: datetime
    ) -> tuple[UUID, int]:
        require_transaction(self.session)
        state = self.session.get(PublicationSyncState, owner_id)
        if state is None:
            return UUID(int=0), 0
        pending = self.session.scalar(
            select(func.min(PublicationSelectedChange.sequence)).where(
                PublicationSelectedChange.owner_id == owner_id,
                PublicationSelectedChange.epoch == state.epoch,
                PublicationSelectedChange.visible_at > now,
            )
        )
        return state.epoch, (pending - 1 if pending is not None else state.sequence)

    def selected_snapshot_in_transaction(
        self, *, owner_id: UUID, now: datetime, limit: int = 100, cursor: str | None = None
    ) -> SelectedSnapshotView:
        epoch, watermark = self.effective_sequence_in_transaction(owner_id=owner_id, now=now)
        scope = {"owner": owner_id, "type": "selected_snapshot"}
        after: UUID | None = None
        anchor = watermark
        if cursor:
            data = decode_cursor(cursor, scope)
            try:
                if UUID(data["epoch"]) != epoch:
                    raise ApplicationError("publication_epoch_conflict")
                anchor = int(data["sequence"])
                after = UUID(data["after"])
                if not 0 <= anchor <= watermark:
                    raise ValueError("sequence")
            except (ValueError, KeyError, TypeError) as error:
                raise ApplicationError("invalid_publication_cursor") from error
        if not 1 <= limit <= 100:
            raise ApplicationError("invalid_publication_input")
        query = select(PublicationRecord).where(
            PublicationRecord.owner_id == owner_id,
            PublicationRecord.selected.is_(True),
            PublicationRecord.last_sequence <= anchor,
        )
        items: list[PublicItemView] = []
        more = False
        last: UUID | None = None
        for _ in range(20):
            batch = query.where(PublicationRecord.content_id > after) if after else query
            rows = list(
                self.session.scalars(batch.order_by(PublicationRecord.content_id).limit(100))
            )
            live = self._live(owner_id=owner_id, rows=rows, now=now)
            for row in rows:
                after = last = row.content_id
                value = live.get(row.content_id)
                if value:
                    projection = value[0]
                    if (
                        projection.visibility == "public"
                        and projection.eligible
                        and projection.selected
                        and projection.visible_after
                        and projection.visible_after <= now
                    ):
                        items.append(self.item(projection))
                if len(items) >= limit:
                    more = True
                    break
            if len(items) >= limit or len(rows) < 100:
                break
            more = True
        return SelectedSnapshotView(
            epoch=epoch,
            sequence=anchor,
            items=items,
            next_cursor=encode_cursor(scope, {"epoch": epoch, "sequence": anchor, "after": last})
            if more and last
            else None,
        )

    def selected_changes_in_transaction(
        self, *, owner_id: UUID, epoch: UUID, since: int, now: datetime, limit: int = 100
    ) -> SelectedChangesPage:
        current, watermark = self.effective_sequence_in_transaction(owner_id=owner_id, now=now)
        if current != epoch:
            raise ApplicationError("publication_epoch_conflict")
        if not 0 <= since <= watermark or not 1 <= limit <= 100:
            raise ApplicationError("invalid_publication_cursor")
        rows = list(
            self.session.scalars(
                select(PublicationSelectedChange)
                .where(
                    PublicationSelectedChange.owner_id == owner_id,
                    PublicationSelectedChange.epoch == epoch,
                    PublicationSelectedChange.sequence > since,
                    PublicationSelectedChange.sequence <= watermark,
                )
                .order_by(PublicationSelectedChange.sequence)
                .limit(limit + 1)
            )
        )
        records = list(
            self.session.scalars(
                select(PublicationRecord).where(
                    PublicationRecord.owner_id == owner_id,
                    PublicationRecord.content_id.in_({row.content_id for row in rows[:limit]}),
                )
            )
        )
        live = self._live(owner_id=owner_id, rows=records, now=now)
        changes = []
        for row in rows[:limit]:
            value = live.get(row.content_id)
            item = None
            if row.operation == "upsert" and value:
                projection = value[0]
                if (
                    projection.visibility == "public"
                    and projection.selected
                    and projection.eligible
                    and projection.visible_after
                    and projection.visible_after <= now
                ):
                    item = self.item(projection)
            changes.append(
                SelectedChangeView(
                    sequence=row.sequence,
                    operation="upsert" if item else "remove",
                    content_id=row.content_id,
                    changed_at=row.changed_at,
                    item=item,
                )
            )
        delivered = rows[limit - 1].sequence if len(rows) > limit else watermark
        return SelectedChangesPage(
            epoch=epoch,
            sequence=delivered,
            changes=changes,
            next_cursor=encode_cursor(
                {"owner": owner_id, "type": "changes"}, {"epoch": epoch, "since": delivered}
            )
            if len(rows) > limit
            else None,
        )


def list_report_candidates_in_transaction(
    session: Session, *, owner_id: UUID, start: datetime, end: datetime, now: datetime
) -> list[ReportPublicationCandidate]:
    require_transaction(session)
    if (
        any(value.utcoffset() is None for value in (start, end, now))
        or not start < end
        or end - start > timedelta(days=32)
    ):
        raise ApplicationError("invalid_publication_input")
    reader = PublicationReadingService(session)
    query = (
        select(PublicationRecord)
        .where(
            PublicationRecord.owner_id == owner_id,
            PublicationRecord.selected.is_(True),
            PublicationRecord.timeline_at >= start,
            PublicationRecord.timeline_at < end,
        )
        .order_by(PublicationRecord.content_id)
    )
    result = []
    after: UUID | None = None
    while True:
        rows = list(
            session.scalars(
                (query.where(PublicationRecord.content_id > after) if after else query).limit(500)
            )
        )
        live = reader._live(owner_id=owner_id, rows=rows, now=now)
        for row in rows:
            value = live.get(row.content_id)
            if value:
                projection = value[0]
                if (
                    projection.visibility == "public"
                    and projection.eligible
                    and projection.selected
                    and projection.summary
                    and projection.visible_after
                    and projection.visible_after <= now
                ):
                    result.append(
                        ReportPublicationCandidate(
                            **frozen_reference(projection).model_dump(),
                            title_zh=projection.title,
                            summary_zh=projection.summary,
                            source_key=projection.source_key,
                            source_name=projection.source_name,
                            source_kind=projection.source_kind,
                            first_party=projection.first_party,
                            url=projection.url,
                            category=projection.category,
                            tags=projection.tags,
                            score=projection.score,
                            timeline_at=projection.timeline_at,
                            backfill=projection.backfill,
                        )
                    )
        if len(rows) < 500:
            break
        after = rows[-1].content_id
    return result


def validate_report_candidates_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    references: tuple[FrozenPublicationReference, ...],
    now: datetime,
) -> PublicationValidationView:
    require_transaction(session)
    reader = PublicationReadingService(session)
    invalid = []
    for offset in range(0, len(references), 500):
        batch = references[offset : offset + 500]
        rows = list(
            session.scalars(
                select(PublicationRecord).where(
                    PublicationRecord.owner_id == owner_id,
                    PublicationRecord.content_id.in_({ref.content_id for ref in batch}),
                )
            )
        )
        live = reader._live(owner_id=owner_id, rows=rows, now=now)
        for ref in batch:
            value = live.get(ref.content_id)
            if (
                value is None
                or frozen_reference(value[0]) != ref
                or value[0].visibility != "public"
                or not value[0].eligible
                or not value[0].selected
                or not value[0].summary
                or not value[0].visible_after
                or value[0].visible_after > now
            ):
                invalid.append(ref.content_id)
    return PublicationValidationView(
        valid=not invalid,
        invalid_content_ids=list(dict.fromkeys(invalid)),
        reason="publication_changed_or_unavailable" if invalid else "valid",
    )


def full_text_grant_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    content_id: UUID,
    content_version_id: UUID,
    policy_revision: int,
    now: datetime,
) -> FullTextGrantView:
    require_transaction(session)
    reader = PublicationReadingService(session)
    row = session.get(PublicationRecord, (owner_id, content_id))
    value = reader._live(owner_id=owner_id, rows=[row] if row else [], now=now).get(content_id)
    if (
        value is None
        or value[0].content_version_id != content_version_id
        or value[0].policy_revision != policy_revision
    ):
        return FullTextGrantView(
            granted=False, reference=None, body=None, reason="version_or_permission_changed"
        )
    projection, snapshot = value
    granted = (
        projection.visibility == "public"
        and projection.selected
        and projection.eligible
        and projection.body_mode == "full"
        and bool(projection.visible_after and projection.visible_after <= now)
    )
    policy = session.get(PublicationSourcePolicy, (owner_id, projection.source_key))
    assert policy is not None
    body, body_format, body_sha256, metadata_media = (
        _fixed_body_in_transaction(session, owner_id=owner_id, snapshot=snapshot, now=now)
        if granted
        else ("", "text", "", [])
    )
    return FullTextGrantView(
        granted=granted,
        reference=frozen_reference(projection) if granted else None,
        body=body if granted else None,
        body_format=body_format,
        body_sha256=body_sha256 if granted else None,
        media=metadata_media if granted else [],
        reason="granted" if granted else "not_selected_public_fulltext",
    )
