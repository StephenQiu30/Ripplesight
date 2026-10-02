"""API-facing use cases own transactions; formats consume only guarded reading DTOs."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from core.errors import ApplicationError
from jobs.schemas import JobAcceptanceInput, JobObservationContext
from jobs.services import JobService
from publication.edition_schemas import (
    PublicDailyCalendarView,
    PublicEditionCatalogueView,
    PublicEditionNavigationView,
)
from publication.exports import (
    agent_instructions,
    item_jsonld,
    item_markdown,
    list_markdown,
    render_edition_rss,
    render_rss,
    render_sitemap,
    render_sitemap_index,
    render_sitemap_paths,
)
from publication.group_schemas import (
    PublicDevelopmentsPage,
    PublicFactReportsPage,
    PublicReadingFilters,
    PublicTimelinePage,
)
from publication.publication_models import (
    PublicationRecord,
    PublicationRepublishRun,
    PublicationSourcePolicy,
)
from publication.reading import PublicationReadingService, public_item
from publication.schemas import (
    Category,
    PublicationOverrideInput,
    PublicEditionSectionView,
    PublicEditionThemeView,
    PublicEditionView,
    PublicItemDetailView,
    PublicItemsPage,
    PublicItemView,
    PublicStoriesPage,
    PublicStoryView,
    PublishResultView,
    RepublishInput,
    RepublishRunView,
    SelectedChangesPage,
    SelectedSnapshotView,
    SharePage,
    SourcePolicyInput,
    SourcePolicyView,
)
from publication.search import search_in_transaction
from publication.services import PublicationService, policy_view
from publication.stories import hot_stories_in_transaction, public_stories_in_transaction
from publication.topic_schemas import PublicTopicDirectoryView, PublicTopicPageView

SITEMAP_SHARD_SIZE = 50_000


class PublicationApplicationService:
    def __init__(
        self,
        session: Session,
        *,
        origin: str = "http://127.0.0.1:8667",
        indexing_enabled: bool = False,
    ) -> None:
        self.session, self.origin, self.indexing_enabled = session, origin, indexing_enabled

    @contextmanager
    def _read(self) -> Iterator[PublicationReadingService]:
        if self.session.in_transaction():
            yield PublicationReadingService(self.session, indexing_enabled=self.indexing_enabled)
        else:
            with self.session.begin():
                self.session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
                self.session.execute(text("SET TRANSACTION READ ONLY"))
                yield PublicationReadingService(
                    self.session, indexing_enabled=self.indexing_enabled
                )

    def items(
        self,
        *,
        owner_id: UUID,
        window: Literal["24h", "7d"] = "24h",
        mode: Literal["selected", "all"] = "selected",
        by: Literal["timeline", "published"] = "timeline",
        category: Category | None = None,
        channel: Literal["news", "x", "firstParty"] | None = None,
        source_key: str | None = None,
        tag: str | None = None,
        topic: str | None = None,
        q: str | None = None,
        search_order: Literal["relevance", "time"] = "relevance",
        limit: int = 50,
        cursor: str | None = None,
        now: datetime | None = None,
    ) -> PublicItemsPage:
        at = now or datetime.now(UTC)
        with self._read() as reader:
            if q is not None:
                # Search has its own bound and cursor; filters are applied by that same query.
                return search_in_transaction(
                    reader,
                    owner_id=owner_id,
                    query=q,
                    search_order=search_order,
                    now=at,
                    window=window,
                    selected=mode == "selected",
                    limit=limit,
                    cursor=cursor,
                    category=category,
                    channel=channel,
                    source_key=source_key,
                    tag=tag,
                    topic=topic,
                )
            return reader.items_in_transaction(
                owner_id=owner_id,
                now=at,
                window=window,
                selected=mode == "selected",
                by=by,
                category=category,
                channel=channel,
                source_key=source_key,
                tag=tag,
                topic=topic,
                limit=limit,
                cursor=cursor,
            )

    def timeline(
        self,
        *,
        owner_id: UUID,
        filters: PublicReadingFilters,
        limit: int = 20,
        cursor: str | None = None,
        now: datetime | None = None,
    ) -> PublicTimelinePage:
        from publication.reading_groups import timeline_in_transaction

        with self._read():
            return timeline_in_transaction(
                self.session,
                owner_id=owner_id,
                filters=filters,
                limit=limit,
                cursor=cursor,
                now=now or datetime.now(UTC),
            )

    def fact_reports(
        self,
        *,
        owner_id: UUID,
        fact_id: UUID,
        filters: PublicReadingFilters,
        limit: int = 20,
        cursor: str | None = None,
        revision: str | None = None,
        now: datetime | None = None,
    ) -> PublicFactReportsPage:
        from publication.reading_groups import fact_reports_in_transaction

        with self._read():
            return fact_reports_in_transaction(
                self.session,
                owner_id=owner_id,
                fact_id=fact_id,
                filters=filters,
                limit=limit,
                cursor=cursor,
                revision=revision,
                now=now or datetime.now(UTC),
            )

    def developments(
        self,
        *,
        owner_id: UUID,
        event_id: UUID,
        filters: PublicReadingFilters,
        limit: int = 20,
        cursor: str | None = None,
        revision: str | None = None,
        now: datetime | None = None,
    ) -> PublicDevelopmentsPage:
        from publication.reading_groups import developments_in_transaction

        with self._read():
            return developments_in_transaction(
                self.session,
                owner_id=owner_id,
                event_id=event_id,
                filters=filters,
                limit=limit,
                cursor=cursor,
                revision=revision,
                now=now or datetime.now(UTC),
            )

    def topic_directory(
        self, *, owner_id: UUID, now: datetime | None = None
    ) -> PublicTopicDirectoryView:
        from publication.topics import topic_directory_in_transaction

        with self._read():
            return topic_directory_in_transaction(
                self.session,
                owner_id=owner_id,
                now=now or datetime.now(UTC),
                indexing_enabled=self.indexing_enabled,
            )

    def topic_page(
        self, *, owner_id: UUID, slug: str, page: int = 1, now: datetime | None = None
    ) -> PublicTopicPageView:
        from publication.topics import topic_page_in_transaction

        with self._read():
            return topic_page_in_transaction(
                self.session,
                owner_id=owner_id,
                slug=slug,
                page=page,
                now=now or datetime.now(UTC),
                indexing_enabled=self.indexing_enabled,
            )

    def detail(
        self,
        *,
        owner_id: UUID,
        content_id: UUID,
        now: datetime | None = None,
        redistribute: bool = False,
    ) -> PublicItemDetailView:
        with self._read() as reader:
            detail = reader.detail_in_transaction(
                owner_id=owner_id,
                content_id=content_id,
                now=now or datetime.now(UTC),
                redistribute=redistribute,
            )
            if detail is None:
                raise ApplicationError("resource_not_found")
            if redistribute and not detail.syndicate_fulltext:
                detail = detail.model_copy(update={"body": None})
            return detail

    def edition_catalogue(
        self,
        *,
        owner_id: UUID,
        kind: Literal["daily", "weekly", "monthly"],
        before_key: str | None = None,
        limit: int = 20,
        now: datetime | None = None,
    ) -> PublicEditionCatalogueView:
        from publication.edition_catalogue import catalogue_in_transaction

        with self._read():
            try:
                return catalogue_in_transaction(
                    self.session,
                    owner_id=owner_id,
                    kind=kind,
                    now=now or datetime.now(UTC),
                    indexing_enabled=self.indexing_enabled,
                    before_key=before_key,
                    limit=limit,
                )
            except ValueError as error:
                raise ApplicationError("invalid_publication_input") from error

    def edition_navigation(
        self,
        *,
        owner_id: UUID,
        kind: Literal["daily", "weekly", "monthly"],
        key: str,
        now: datetime | None = None,
    ) -> PublicEditionNavigationView:
        from publication.edition_catalogue import navigation_in_transaction

        with self._read():
            try:
                return navigation_in_transaction(
                    self.session,
                    owner_id=owner_id,
                    kind=kind,
                    key=key,
                    now=now or datetime.now(UTC),
                    indexing_enabled=self.indexing_enabled,
                )
            except ValueError as error:
                raise ApplicationError("invalid_publication_input") from error

    def daily_calendar(
        self,
        *,
        owner_id: UUID,
        month: str,
        now: datetime | None = None,
    ) -> PublicDailyCalendarView:
        from publication.edition_catalogue import daily_calendar_in_transaction

        with self._read():
            try:
                return daily_calendar_in_transaction(
                    self.session,
                    owner_id=owner_id,
                    month=month,
                    now=now or datetime.now(UTC),
                    indexing_enabled=self.indexing_enabled,
                )
            except ValueError as error:
                raise ApplicationError("invalid_publication_input") from error

    def selected_snapshot(
        self,
        *,
        owner_id: UUID,
        limit: int = 100,
        cursor: str | None = None,
        now: datetime | None = None,
    ) -> SelectedSnapshotView:
        with self._read() as reader:
            return reader.selected_snapshot_in_transaction(
                owner_id=owner_id, limit=limit, cursor=cursor, now=now or datetime.now(UTC)
            )

    def selected_changes(
        self,
        *,
        owner_id: UUID,
        epoch: UUID,
        since: int,
        limit: int = 100,
        now: datetime | None = None,
    ) -> SelectedChangesPage:
        with self._read() as reader:
            return reader.selected_changes_in_transaction(
                owner_id=owner_id,
                epoch=epoch,
                since=since,
                limit=limit,
                now=now or datetime.now(UTC),
            )

    def story(
        self, *, owner_id: UUID, event_id: UUID, now: datetime | None = None
    ) -> PublicStoryView:
        with self._read() as reader:
            values = public_stories_in_transaction(
                reader, owner_id=owner_id, event_ids=(event_id,), now=now or datetime.now(UTC)
            )
            if not values:
                raise ApplicationError("resource_not_found")
            return values[0].model_copy(
                update={"canonical_url": f"{self.origin}/discover/stories/{values[0].id}"}
            )

    def hot(
        self, *, owner_id: UUID, limit: int = 10, now: datetime | None = None
    ) -> PublicStoriesPage:
        with self._read() as reader:
            return hot_stories_in_transaction(
                reader, owner_id=owner_id, limit=limit, now=now or datetime.now(UTC)
            )

    def feed(
        self,
        *,
        owner_id: UUID,
        kind: Literal["selected", "selected-full", "all"] = "selected",
        category: Category | None = None,
        now: datetime | None = None,
    ) -> str:
        at = now or datetime.now(UTC)
        with self._read() as reader:
            from publication.listing import iter_current_publications_in_transaction

            details = []
            for member in iter_current_publications_in_transaction(
                self.session, owner_id=owner_id, now=at, order="timeline", ends_at=at
            ):
                projection = member.projection
                if (
                    (kind != "all" and not projection.selected)
                    or (category and projection.category != category)
                    or (
                        projection.selected
                        and (not projection.visible_after or projection.visible_after > at)
                    )
                ):
                    continue
                detail = reader.detail_in_transaction(
                    owner_id=owner_id, content_id=projection.content_id, now=at, redistribute=True
                )
                if detail:
                    details.append(detail)
                if len(details) == 50:
                    break
            path = (
                "/feed.xml"
                if kind == "selected"
                else "/feed/full.xml"
                if kind == "selected-full"
                else "/feed/all.xml"
            )
            if category:
                path = f"/feed/{'full/' if kind == 'selected-full' else ''}category/{category}.xml"
            return render_rss(
                details,
                origin=self.origin,
                self_path=path,
                title="HotKey精选" if kind != "all" else "HotKey全部资讯",
                now=at,
                include_content=kind == "selected-full",
            )

    def markdown(
        self,
        *,
        owner_id: UUID,
        content_id: UUID,
        now: datetime | None = None,
        redistribute: bool = False,
    ) -> str:
        detail = self.detail(
            owner_id=owner_id, content_id=content_id, now=now, redistribute=redistribute
        )
        output = item_markdown(detail, origin=self.origin, redistribute=redistribute)
        if output is None:
            raise ApplicationError("resource_not_found")
        return output

    def latest_markdown(self, *, owner_id: UUID, now: datetime | None = None) -> str:
        return list_markdown(
            self.items(owner_id=owner_id, now=now).items, title="HotKey精选", origin=self.origin
        )

    def jsonld(self, *, owner_id: UUID, content_id: UUID, now: datetime | None = None) -> str:
        output = item_jsonld(
            self.detail(owner_id=owner_id, content_id=content_id, now=now), origin=self.origin
        )
        if output is None:
            raise ApplicationError("resource_not_found")
        return output

    def sitemap(self, *, owner_id: UUID, now: datetime | None = None) -> str:
        if not self.indexing_enabled:
            return render_sitemap_index(0, origin=self.origin)
        at = now or datetime.now(UTC)
        with self._read():
            count = (
                self.session.scalar(
                    select(func.count())
                    .select_from(PublicationRecord)
                    .where(PublicationRecord.owner_id == owner_id)
                )
                or 0
            )
            shards = (count + SITEMAP_SHARD_SIZE - 1) // SITEMAP_SHARD_SIZE
            stories = len(self._sitemap_story_ids(owner_id=owner_id, now=at))
            reports = len(self._sitemap_edition_keys(owner_id=owner_id, now=at))
            topics = int(
                any(
                    topic.indexable
                    for topic in self.topic_directory(owner_id=owner_id, now=at).topics
                )
            )
            story_shards = (stories + SITEMAP_SHARD_SIZE - 1) // SITEMAP_SHARD_SIZE
            report_shards = (reports + SITEMAP_SHARD_SIZE - 1) // SITEMAP_SHARD_SIZE
            if shards + story_shards + report_shards + topics > 50_000:
                raise ApplicationError("invalid_publication_input")
            return render_sitemap_index(
                shards,
                origin=self.origin,
                stories=story_shards,
                reports=report_shards,
                topics=topics,
            )

    def _sitemap_story_ids(self, *, owner_id: UUID, now: datetime) -> list[UUID]:
        from events.reads import list_story_indexing_changes_in_transaction

        after = None
        identities: set[UUID] = set()
        while True:
            batch = list_story_indexing_changes_in_transaction(
                self.session, owner_id=owner_id, after=after, until=now, limit=500
            )
            identities.update(row.event_id for row in batch)
            if len(batch) < 500:
                return sorted(identities)
            after = (batch[-1].changed_at, batch[-1].event_id)

    def _sitemap_edition_keys(
        self, *, owner_id: UUID, now: datetime
    ) -> list[tuple[Literal["daily", "weekly", "monthly"], str]]:
        from reports.edition_reading import list_edition_indexing_changes_in_transaction

        after = (datetime.min.replace(tzinfo=UTC), UUID(int=0))
        identities: set[tuple[Literal["daily", "weekly", "monthly"], str]] = set()
        while True:
            batch = list_edition_indexing_changes_in_transaction(
                self.session, owner_id=owner_id, after=after, until=now, limit=500
            )
            identities.update((row.kind, row.key) for row in batch)
            if len(batch) < 500:
                return sorted(identities)
            after = (batch[-1].changed_at, batch[-1].edition_id)

    def sitemap_collection_shard(
        self,
        *,
        owner_id: UUID,
        collection: Literal["stories", "reports", "topics"],
        shard: int,
        now: datetime | None = None,
    ) -> str:
        if collection not in {"stories", "reports", "topics"} or not 0 <= shard <= 999_999:
            raise ApplicationError("invalid_publication_input")
        if not self.indexing_enabled:
            return render_sitemap_paths([], origin=self.origin)
        at = now or datetime.now(UTC)
        start, end = shard * SITEMAP_SHARD_SIZE, (shard + 1) * SITEMAP_SHARD_SIZE
        paths: list[str] = []
        with self._read() as reader:
            if collection == "stories":
                ids = self._sitemap_story_ids(owner_id=owner_id, now=at)[start:end]
                if not ids:
                    raise ApplicationError("resource_not_found")
                for offset in range(0, len(ids), 100):
                    paths.extend(
                        f"/discover/stories/{story.id}"
                        for story in public_stories_in_transaction(
                            reader,
                            owner_id=owner_id,
                            event_ids=tuple(ids[offset : offset + 100]),
                            now=at,
                        )
                        if story.indexable
                    )
            elif collection == "reports":
                keys = self._sitemap_edition_keys(owner_id=owner_id, now=at)[start:end]
                if not keys:
                    raise ApplicationError("resource_not_found")
                for kind, key in keys:
                    try:
                        edition = self.edition(owner_id=owner_id, kind=kind, key=key, now=at)
                    except ApplicationError as error:
                        if error.code != "resource_not_found":
                            raise
                        continue
                    if edition.indexable:
                        paths.append(f"/reports/{kind}/{key}")
            else:
                topics = sorted(
                    self.topic_directory(owner_id=owner_id, now=at).topics,
                    key=lambda value: value.slug,
                )[start:end]
                if not topics:
                    raise ApplicationError("resource_not_found")
                paths.extend(
                    f"/discover/topics/{topic.slug}" for topic in topics if topic.indexable
                )
            return render_sitemap_paths(paths, origin=self.origin)

    def sitemap_shard(self, *, owner_id: UUID, shard: int, now: datetime | None = None) -> str:
        if not 0 <= shard <= 999_999:
            raise ApplicationError("invalid_publication_input")
        if not self.indexing_enabled:
            return render_sitemap([], origin=self.origin)
        at = now or datetime.now(UTC)
        with self._read() as reader:
            # Partition stable stored IDs, never visible ranks: withdrawal leaves a hole.
            # Freeze only bounded IDs in one query; large projection JSON is read 500 at a time.
            identities = list(
                self.session.scalars(
                    select(PublicationRecord.content_id)
                    .where(PublicationRecord.owner_id == owner_id)
                    .order_by(PublicationRecord.content_id)
                    .offset(shard * SITEMAP_SHARD_SIZE)
                    .limit(SITEMAP_SHARD_SIZE)
                )
            )
            if not identities:
                raise ApplicationError("resource_not_found")
            items: list[PublicItemView] = []
            for offset in range(0, len(identities), 500):
                rows = list(
                    self.session.scalars(
                        select(PublicationRecord)
                        .where(
                            PublicationRecord.owner_id == owner_id,
                            PublicationRecord.content_id.in_(identities[offset : offset + 500]),
                        )
                        .order_by(PublicationRecord.content_id)
                    )
                )
                live = reader._live(owner_id=owner_id, rows=rows, now=at)
                items.extend(public_item(value[0]) for value in live.values() if value[0].indexable)
            return render_sitemap(items, origin=self.origin)

    def instructions(self) -> str:
        return agent_instructions(origin=self.origin)

    def policies(self, *, owner_id: UUID) -> list[SourcePolicyView]:
        with self._read():
            return [
                policy_view(row)
                for row in self.session.scalars(
                    select(PublicationSourcePolicy)
                    .where(PublicationSourcePolicy.owner_id == owner_id)
                    .order_by(PublicationSourcePolicy.source_key)
                )
            ]

    def save_policy(
        self, *, owner_id: UUID, source_key: str, command: SourcePolicyInput
    ) -> SourcePolicyView:
        self.session.rollback()
        with self.session.begin():
            return PublicationService(
                self.session, indexing_enabled=self.indexing_enabled
            ).save_source_policy_in_transaction(
                owner_id=owner_id, actor_id=owner_id, source_key=source_key, command=command
            )

    def override(
        self, *, owner_id: UUID, content_id: UUID, command: PublicationOverrideInput
    ) -> PublishResultView:
        self.session.rollback()
        with self.session.begin():
            return PublicationService(
                self.session, indexing_enabled=self.indexing_enabled
            ).override_in_transaction(
                owner_id=owner_id, actor_id=owner_id, content_id=content_id, command=command
            )

    def republish(
        self, *, owner_id: UUID, source_key: str, command: RepublishInput
    ) -> RepublishRunView:
        self.session.rollback()
        with self.session.begin():
            service = PublicationService(self.session, indexing_enabled=self.indexing_enabled)
            service._lock(owner_id)
            policy = self.session.get(PublicationSourcePolicy, (owner_id, source_key))
            if policy is None:
                raise ApplicationError("resource_not_found")
            if policy.revision != command.expected_policy_revision:
                raise ApplicationError("publication_revision_conflict")
            run_id = uuid5(command.operation_id, f"publication:{source_key}")
            accepted = JobService(self.session).accept_in_transaction(
                owner_id=owner_id,
                command=JobAcceptanceInput(
                    operation_id=command.operation_id,
                    kind="publication.republish",
                    observation=JobObservationContext(
                        configuration_ref=f"publication-source:{source_key}",
                        configuration_version=policy.revision,
                    ),
                    scope={
                        "republish_run_id": str(run_id),
                        "source_key": source_key,
                        "policy_revision": policy.revision,
                    },
                ),
            )
            identity = service.create_republish_in_transaction(
                owner_id=owner_id,
                source_key=source_key,
                job_id=accepted.id,
                operation_id=command.operation_id,
                run_id=run_id,
            )
            row = self.session.scalar(
                select(PublicationRepublishRun).where(
                    PublicationRepublishRun.owner_id == owner_id,
                    PublicationRepublishRun.id == identity,
                )
            )
            assert row is not None
            return RepublishRunView.model_validate(row)

    def republish_status(self, *, owner_id: UUID, run_id: UUID) -> RepublishRunView:
        with self._read():
            row = self.session.scalar(
                select(PublicationRepublishRun).where(
                    PublicationRepublishRun.owner_id == owner_id,
                    PublicationRepublishRun.id == run_id,
                )
            )
            if row is None:
                raise ApplicationError("resource_not_found")
            return RepublishRunView.model_validate(row)

    def edition(
        self,
        *,
        owner_id: UUID,
        kind: Literal["daily", "weekly", "monthly"] = "daily",
        key: str | None = None,
        now: datetime | None = None,
    ) -> PublicEditionView:
        from reports.edition_reading import load_current_edition_in_transaction
        from reports.edition_rules import period_window

        if key is not None:
            try:
                period_window(kind, key)
            except ValueError as error:
                raise ApplicationError("invalid_publication_input") from error

        at = now or datetime.now(UTC)
        with self._read() as reader:
            edition = load_current_edition_in_transaction(
                self.session, owner_id=owner_id, kind=kind, key=key, now=at
            )
            if (
                edition is None
                or not edition.content
                or not edition.title
                or not edition.body_markdown
            ):
                raise ApplicationError("resource_not_found")
            entries = []
            for entry in edition.content.entries:
                projection = reader.projection_in_transaction(
                    owner_id=owner_id, content_id=entry.content_id, now=at
                )
                if projection is None:
                    raise ApplicationError("resource_not_found")
                entries.append(reader.item(projection))
            return PublicEditionView(
                id=edition.id,
                kind=edition.kind,
                key=edition.key,
                revision=edition.revision,
                title=edition.title,
                lead=edition.content.lead,
                window_start=edition.window_start,
                window_end=edition.window_end,
                created_at=edition.created_at,
                highlights=edition.content.highlights,
                sections=[
                    PublicEditionSectionView.model_validate(item.model_dump())
                    for item in edition.content.sections
                ],
                flashes=edition.content.flashes,
                themes=[
                    PublicEditionThemeView.model_validate(item.model_dump())
                    for item in edition.content.themes
                ],
                entries=entries,
                metrics=edition.content.metrics.model_dump(),
                body_markdown=edition.body_markdown,
                indexable=self.indexing_enabled
                and bool(entries)
                and all(item.indexable for item in entries),
                canonical_url=f"{self.origin}/reports/{kind}/{edition.key}",
            )

    def edition_markdown(
        self,
        *,
        owner_id: UUID,
        kind: Literal["daily", "weekly", "monthly"] = "daily",
        key: str | None = None,
        now: datetime | None = None,
    ) -> str:
        edition = self.edition(owner_id=owner_id, kind=kind, key=key, now=now)
        return (
            edition.body_markdown + f"\n\n阅读与归因: {self.origin}/reports/{kind}/{edition.key}\n"
        )

    def edition_feed(
        self,
        *,
        owner_id: UUID,
        kind: Literal["daily", "weekly", "monthly"] = "daily",
        now: datetime | None = None,
    ) -> str:
        from reports.edition_reading import list_current_editions_in_transaction

        at = now or datetime.now(UTC)
        with self._read():
            editions = list_current_editions_in_transaction(
                self.session, owner_id=owner_id, kind=kind, limit=50, now=at
            )
            values = []
            for edition in editions:
                try:
                    values.append(
                        self.edition(owner_id=owner_id, kind=kind, key=edition.key, now=at)
                    )
                except ApplicationError as error:
                    if error.code != "resource_not_found":
                        raise
            return render_edition_rss(values, origin=self.origin, kind=kind, now=at)

    def robots(self) -> str:
        if not self.indexing_enabled:
            return "User-agent: *\nDisallow: /\n"
        return (
            f"User-agent: *\nDisallow: /api/\nDisallow: /ops/\nSitemap: {self.origin}/sitemap.xml\n"
        )

    def share_page(self, *, page: SharePage = "site") -> bytes:
        from publication.share_images import ShareCard, render_share_png

        pages = {
            "site": ("HotKey", "关注热点与真实变化", "经许可的来源、事实、精选与日周月刊", "/"),
            "all": (
                "公开动态",
                "所有公开来源的最新动态",
                "按来源、类别、标签与时间检索",
                "/discover?mode=all",
            ),
            "hot": (
                "事件热度",
                "公开来源正在关注的事实",
                "固定材料、热度、趋势和来源组成",
                "/discover",
            ),
            "daily": (
                "日报",
                "一天的重要变化",
                "前一完整自然日的精选与固定引用",
                "/editions?kind=daily",
            ),
            "weekly": (
                "周报",
                "一周大事",
                "一周的主线、发布与值得回看的事实",
                "/editions?kind=weekly",
            ),
            "monthly": ("月报", "一个月的变化", "月度主线与关键事实回顾", "/editions?kind=monthly"),
            "topics": (
                "行业专题",
                "长期追踪的方向",
                "公司、研究方向与内容形态",
                "/discover/topics",
            ),
            "leaderboard": (
                "模型榜",
                "多家公开评测的共识排名",
                "缺测不补零,价格不改变排名",
                "/leaderboard",
            ),
            "codex-reset": (
                "Codex 公告",
                "额度重置的公开证据",
                "时间窗口、适用范围和原始公告",
                "/codex-resets",
            ),
            "about": ("关于", "关于 HotKey", "项目范围、出处与当前使用边界", "/about"),
            "terms": ("使用规则", "HotKey 使用规则", "页面、公开接口与分发的使用范围", "/terms"),
            "privacy": (
                "隐私说明",
                "HotKey 隐私说明",
                "浏览器本机数据、日志与反馈资料",
                "/privacy",
            ),
            "changelog": (
                "更新日志",
                "HotKey 更新记录",
                "已实现的功能、变更与证据边界",
                "/changelog",
            ),
            "feedback": ("反馈", "反馈与更正", "内容、功能和来源更正或撤回请求", "/feedback"),
            "agent": (
                "Agent 接入",
                "让 Agent 使用公开资料",
                "只读 MCP、RSS、REST 与 Markdown",
                "/agent",
            ),
            "contact": ("联系", "联系 HotKey", "当前启用的真实联系资料", "/contact"),
        }
        value = pages.get(page)
        if value is None:
            raise ApplicationError("resource_not_found")
        kicker, title, summary, path = value
        return render_share_png(
            ShareCard(kicker=kicker, title=title, summary=summary, canonical_url=self.origin + path)
        )

    def share_item(
        self, *, owner_id: UUID, content_id: UUID, poster: bool = False, now: datetime | None = None
    ) -> bytes:
        from publication.share_images import ShareCard, render_share_png

        at = now or datetime.now(UTC)
        with self._read() as reader:
            projection = reader.projection_in_transaction(
                owner_id=owner_id, content_id=content_id, now=at
            )
            if projection is None or projection.visibility != "public":
                raise ApplicationError("resource_not_found")
            item = public_item(projection)
            date = item.timeline_at.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
            return render_share_png(
                ShareCard(
                    kicker="精选阅读" if item.selected else "公开动态",
                    title=item.title,
                    summary=item.summary or "",
                    meta=f"{item.source.name} · {date}",
                    canonical_url=self.origin + item.reading_url,
                    score=item.score if item.selected else None,
                ),
                poster=poster,
            )

    def share_story(
        self, *, owner_id: UUID, event_id: UUID, poster: bool = False, now: datetime | None = None
    ) -> bytes:
        from publication.share_images import ShareCard, render_share_png

        story = self.story(owner_id=owner_id, event_id=event_id, now=now)
        sources = len({item.source.key for item in story.reports})
        return render_share_png(
            ShareCard(
                kicker="公开事件",
                title=story.title,
                summary=story.latest_progress or story.summary,
                meta=f"{sources} 个展示来源 · {len(story.reports)} 篇展示报道",
                canonical_url=self.origin + f"/discover/stories/{story.id}",
            ),
            poster=poster,
        )

    def share_edition(
        self,
        *,
        owner_id: UUID,
        kind: Literal["daily", "weekly", "monthly"],
        key: str,
        poster: bool = False,
        now: datetime | None = None,
    ) -> bytes:
        from publication.share_images import ShareCard, render_share_png

        edition = self.edition(owner_id=owner_id, kind=kind, key=key, now=now)
        return render_share_png(
            ShareCard(
                kicker=f"{kind} · {key}",
                title=edition.title,
                summary=edition.lead,
                meta=f"{len(edition.entries)} 条固定精选 · 修订 {edition.revision}",
                canonical_url=self.origin + f"/reports/{kind}/{key}",
            ),
            poster=poster,
        )

    def share_topic(self, *, owner_id: UUID, slug: str, now: datetime | None = None) -> bytes:
        from publication.share_images import ShareCard, render_share_png

        page = self.topic_page(owner_id=owner_id, slug=slug, page=1, now=now)
        return render_share_png(
            ShareCard(
                kicker="行业专题",
                title=page.topic.name,
                summary=page.topic.definition,
                meta=f"{page.topic.total} 篇当前精选 · 最近30天 {page.topic.recent} 篇",
                canonical_url=self.origin + f"/discover/topics/{slug}",
            )
        )

    def item_poster(self, *, owner_id: UUID, content_id: UUID, now: datetime | None = None) -> str:
        from publication.posters import item_poster

        result = item_poster(
            self.detail(owner_id=owner_id, content_id=content_id, now=now), origin=self.origin
        )
        if result is None:
            raise ApplicationError("resource_not_found")
        return result

    def story_poster(self, *, owner_id: UUID, event_id: UUID, now: datetime | None = None) -> str:
        from publication.posters import story_poster

        return story_poster(
            self.story(owner_id=owner_id, event_id=event_id, now=now), origin=self.origin
        )

    def edition_poster(
        self,
        *,
        owner_id: UUID,
        kind: Literal["daily", "weekly", "monthly"],
        key: str,
        now: datetime | None = None,
    ) -> str:
        from publication.posters import edition_poster

        return edition_poster(
            self.edition(owner_id=owner_id, kind=kind, key=key, now=now), origin=self.origin
        )
