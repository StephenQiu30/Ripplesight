from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4, uuid5

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from connections.schemas import SourceEntryPoint
from connections.services import (
    list_applied_hotlist_presets_in_transaction,
    require_source_connection_version,
)
from content.discovery import KeywordDiscoveryPageCommitService, KeywordRequestMeter
from content.models import HotlistEntryRecord, HotlistSnapshot
from content.schemas import (
    HotlistEntryView,
    HotlistSnapshotSummaryView,
    HotlistSnapshotView,
    HotlistSourceView,
    PersistContentPostInput,
)
from content.services import ContentService
from core.errors import ApplicationError
from evidence.schemas import DataClass
from evidence.services import SourceAccessPolicyService
from jobs.coverage import (
    count_hotlist_gaps_in_transaction,
    load_hotlist_due_for_job_in_transaction,
)
from jobs.execution import ExecutionLease, JobExecutionService, JobProgress
from jobs.schemas import JobStage
from jobs.services import ResourceBudgetService
from monitors.services import ActiveHotlistTopic, MonitorScheduleService, evaluate_monitor_rules
from sources.adapters.web_targets import normalize_public_article_url
from sources.contracts import (
    HotlistEntry,
    HotlistPage,
    SourceCapability,
    SourcePageState,
    SourcePost,
)


def recover_hotlist_usage_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    operation_id: UUID,
    source_key: str,
    finished_at: datetime,
) -> tuple[UUID, ...]:
    return ResourceBudgetService(
        session, clock=lambda: finished_at
    ).recover_abandoned_attempts_in_transaction(
        owner_id=owner_id,
        operation_id=operation_id,
        component_key=f"collector.{source_key}",
        stage="hotlist.request",
        finished_at=finished_at,
    )


def rank_change(rank: int, previous_rank: int | None) -> Literal["new", "up", "down", "same"]:
    if previous_rank is None:
        return "new"
    if rank < previous_rank:
        return "up"
    if rank > previous_rank:
        return "down"
    return "same"


def _rank_identity(url: str) -> str:
    try:
        return normalize_public_article_url(url)
    except ValueError:
        # Older snapshots may contain links admitted before public URL validation.
        return url


def match_hotlist_topics(
    entry: HotlistEntry, topics: Iterable[ActiveHotlistTopic]
) -> tuple[str, ...]:
    return tuple(topic.name for topic in matching_hotlist_topics(entry, topics))


def matching_hotlist_topics(
    entry: HotlistEntry, topics: Iterable[ActiveHotlistTopic]
) -> tuple[ActiveHotlistTopic, ...]:
    text = "\n".join(part for part in (entry.title, entry.summary) if part)
    return tuple(topic for topic in topics if evaluate_monitor_rules(topic.rules, text).matched)


def _post_payload(entry: HotlistEntry, source_key: str) -> dict[str, object]:
    canonical_url = normalize_public_article_url(entry.url)
    external_id = canonical_url
    if len(external_id) > 512:
        external_id = "sha256:" + hashlib.sha256(canonical_url.encode()).hexdigest()
    post = SourcePost(
        source_key=source_key,
        external_id=external_id,
        identity_basis="url_fallback",
        author_external_id=None,
        # Ranking is an observation; source publication time remains on the snapshot entry.
        published_at=None,
        text=entry.summary,
        # A ranking title (with or without a feed summary) is not the full article.
        text_scope="truncated",
        title=entry.title,
        canonical_url=canonical_url,
        like_count=None,
        comment_count=None,
        repost_count=None,
    )
    return KeywordDiscoveryPageCommitService._payload(post)


class HotlistService:
    def __init__(
        self,
        session: Session,
        *,
        lease_seconds: int = 75,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session = session
        self._lease_seconds = lease_seconds
        self._clock = clock or (lambda: datetime.now(UTC))

    def commit_snapshot(
        self,
        *,
        owner_id: UUID,
        lease: ExecutionLease,
        operation_id: UUID,
        source_key: str,
        connection_id: UUID,
        connection_version: int,
        page: HotlistPage,
        meter: KeywordRequestMeter,
    ) -> ExecutionLease:
        if page.source_key != source_key or page.state not in {
            SourcePageState.COMPLETE,
            SourcePageState.EMPTY,
        }:
            raise ValueError("only a completed or empty matching hotlist page may be saved")
        self._session.rollback()
        with self._session.begin():
            execution = JobExecutionService(
                self._session, lease_seconds=self._lease_seconds, clock=self._clock
            )
            current = execution.require_current_operation_in_transaction(
                lease, owner_id=owner_id, operation_id=operation_id
            )
            existing = self._session.scalar(
                select(HotlistSnapshot).where(
                    HotlistSnapshot.owner_id == owner_id,
                    HotlistSnapshot.job_id == lease.job_id,
                )
            )
            if existing is not None:
                if existing.operation_id != operation_id:
                    raise ValueError("existing hotlist snapshot belongs to a different operation")
                return current
            load_hotlist_due_for_job_in_transaction(
                self._session,
                owner_id=owner_id,
                job_id=lease.job_id,
                source_key=source_key,
                operation_id=operation_id,
            )
            require_source_connection_version(
                self._session,
                owner_id=owner_id,
                source_key=source_key,
                connection_id=connection_id,
                connection_version=connection_version,
            )
            policy = SourceAccessPolicyService(self._session, clock=self._clock)
            policy.require_admission_ready_in_transaction(
                owner_id=owner_id,
                source_key=source_key,
                capability=SourceCapability.HOTLIST,
                data_class=DataClass.STRUCTURED,
            )
            topics = MonitorScheduleService(
                self._session
            ).list_active_hotlist_topics_in_transaction(owner_id=owner_id)
            snapshot = HotlistSnapshot(
                id=uuid4(),
                owner_id=owner_id,
                source_key=source_key,
                job_id=lease.job_id,
                operation_id=operation_id,
                observed_at=page.observed_at,
                entry_count=len(page.items),
            )
            self._session.add(snapshot)
            self._session.flush()
            content = ContentService(self._session, clock=self._clock)
            matched_contents: dict[str, UUID] = {}
            for entry in page.items:
                normalized_url = normalize_public_article_url(entry.url)
                matches = matching_hotlist_topics(entry, topics)
                names = tuple(topic.name for topic in matches)
                content_id: UUID | None = None
                if names:
                    content_id = matched_contents.get(normalized_url)
                    if content_id is None:
                        admitted = policy.admit_payload_in_transaction(
                            owner_id=owner_id,
                            source_key=source_key,
                            capability=SourceCapability.HOTLIST,
                            data_class=DataClass.STRUCTURED,
                            collected_at=page.observed_at,
                            payload=_post_payload(entry, source_key),
                        )
                        persisted = content.persist_post_in_transaction(
                            owner_id=owner_id,
                            command=PersistContentPostInput(
                                job_id=lease.job_id,
                                source_operation_id=uuid5(operation_id, normalized_url),
                                connection_id=connection_id,
                                connection_version=connection_version,
                                entry_point=SourceEntryPoint.SCHEDULED,
                                component_name=f"collector.{source_key}",
                                component_version=page.adapter_version,
                                admission=admitted,
                            ),
                        )
                        content_id = matched_contents[normalized_url] = persisted.id
                self._session.add(
                    HotlistEntryRecord(
                        snapshot_id=snapshot.id,
                        owner_id=owner_id,
                        rank=entry.rank,
                        title=entry.title,
                        url=entry.url,
                        summary=entry.summary,
                        heat=entry.heat,
                        published_at=entry.published_at,
                        content_id=content_id,
                        matched_topic_names=list(names),
                        matched_topic_ids=[str(topic.topic_id) for topic in matches],
                    )
                )
            meter.settle_page_in_transaction(
                page=page, owner_id=owner_id, lease=lease, operation_id=operation_id
            )
            renewed = execution.save_checkpoint_in_transaction(
                lease,
                sequence=lease.checkpoint_sequence + 1,
                checkpoint={
                    "snapshot_id": str(snapshot.id),
                    "collection.observed_count": len(page.items),
                },
                progress=JobProgress(stage=JobStage.SAVE, items_saved=len(page.items)),
            )
        meter.confirm_page(renewed)
        return renewed

    def list_sources(self, *, owner_id: UUID) -> tuple[HotlistSourceView, ...]:
        self._session.rollback()
        with self._session.begin():
            applied = list_applied_hotlist_presets_in_transaction(self._session, owner_id=owner_id)
            return tuple(
                HotlistSourceView(
                    source_key=item.source_key,
                    latest_observed_at=self._session.scalar(
                        select(HotlistSnapshot.observed_at)
                        .where(
                            HotlistSnapshot.owner_id == owner_id,
                            HotlistSnapshot.source_key == item.source_key,
                        )
                        .order_by(HotlistSnapshot.observed_at.desc(), HotlistSnapshot.id.desc())
                        .limit(1)
                    ),
                )
                for item in applied
            )

    def get_latest(
        self,
        *,
        owner_id: UUID,
        source_key: str,
        cursor: int | None = None,
        limit: int = 20,
    ) -> HotlistSnapshotView:
        if cursor is not None and cursor < 1:
            raise ApplicationError("resource_not_found")
        self._session.rollback()
        with self._session.begin():
            self._require_applied(owner_id=owner_id, source_key=source_key)
            latest = self._session.scalar(
                select(HotlistSnapshot)
                .where(
                    HotlistSnapshot.owner_id == owner_id,
                    HotlistSnapshot.source_key == source_key,
                )
                .order_by(HotlistSnapshot.observed_at.desc(), HotlistSnapshot.id.desc())
                .limit(1)
            )
            if latest is None:
                raise ApplicationError("resource_not_found")
            return self._snapshot_view(latest, owner_id=owner_id, cursor=cursor, limit=limit)

    def list_history(
        self,
        *,
        owner_id: UUID,
        source_key: str,
        cursor: UUID | None = None,
        limit: int = 20,
    ) -> tuple[tuple[HotlistSnapshotSummaryView, ...], str | None]:
        self._session.rollback()
        with self._session.begin():
            self._require_applied(owner_id=owner_id, source_key=source_key)
            query = select(HotlistSnapshot).where(
                HotlistSnapshot.owner_id == owner_id,
                HotlistSnapshot.source_key == source_key,
            )
            if cursor is not None:
                anchor = self._session.scalar(query.where(HotlistSnapshot.id == cursor))
                if anchor is None:
                    raise ValueError("hotlist cursor does not belong to this source")
                query = query.where(self._older_than(anchor))
            rows = self._session.scalars(
                query.order_by(HotlistSnapshot.observed_at.desc(), HotlistSnapshot.id.desc()).limit(
                    limit + 1
                )
            ).all()
            selected = rows[:limit]
            summaries = tuple(
                self._summary(row, rows[index + 1] if index + 1 < len(rows) else None)
                for index, row in enumerate(selected)
            )
            return summaries, str(selected[-1].id) if len(rows) > limit else None

    def get_historical(
        self,
        *,
        owner_id: UUID,
        source_key: str,
        snapshot_id: UUID,
        cursor: int | None = None,
        limit: int = 20,
    ) -> HotlistSnapshotView:
        self._session.rollback()
        with self._session.begin():
            self._require_applied(owner_id=owner_id, source_key=source_key)
            snapshot = self._session.scalar(
                select(HotlistSnapshot).where(
                    HotlistSnapshot.owner_id == owner_id,
                    HotlistSnapshot.source_key == source_key,
                    HotlistSnapshot.id == snapshot_id,
                )
            )
            if snapshot is None:
                raise ApplicationError("resource_not_found")
            return self._snapshot_view(snapshot, owner_id=owner_id, cursor=cursor, limit=limit)

    def _require_applied(self, *, owner_id: UUID, source_key: str) -> None:
        applied = list_applied_hotlist_presets_in_transaction(self._session, owner_id=owner_id)
        if source_key not in {item.source_key for item in applied}:
            raise ApplicationError("resource_not_found")

    @staticmethod
    def _older_than(snapshot: HotlistSnapshot) -> ColumnElement[bool]:
        return or_(
            HotlistSnapshot.observed_at < snapshot.observed_at,
            and_(
                HotlistSnapshot.observed_at == snapshot.observed_at,
                HotlistSnapshot.id < snapshot.id,
            ),
        )

    def _previous(self, snapshot: HotlistSnapshot) -> HotlistSnapshot | None:
        return self._session.scalar(
            select(HotlistSnapshot)
            .where(
                HotlistSnapshot.owner_id == snapshot.owner_id,
                HotlistSnapshot.source_key == snapshot.source_key,
                self._older_than(snapshot),
            )
            .order_by(HotlistSnapshot.observed_at.desc(), HotlistSnapshot.id.desc())
            .limit(1)
        )

    def _summary(
        self, snapshot: HotlistSnapshot, previous: HotlistSnapshot | None
    ) -> HotlistSnapshotSummaryView:
        due = load_hotlist_due_for_job_in_transaction(
            self._session,
            owner_id=snapshot.owner_id,
            job_id=snapshot.job_id,
            source_key=snapshot.source_key,
            operation_id=snapshot.operation_id,
        )
        gap_count = 0
        if previous is not None:
            prior_due = load_hotlist_due_for_job_in_transaction(
                self._session,
                owner_id=previous.owner_id,
                job_id=previous.job_id,
                source_key=previous.source_key,
                operation_id=previous.operation_id,
            )
            gap_count = count_hotlist_gaps_in_transaction(
                self._session,
                owner_id=snapshot.owner_id,
                source_key=snapshot.source_key,
                previous_due_at=prior_due.due_at,
                due_at=due.due_at,
            )
        return HotlistSnapshotSummaryView(
            snapshot_id=snapshot.id,
            source_key=snapshot.source_key,
            observed_at=snapshot.observed_at,
            due_at=due.due_at,
            entry_count=snapshot.entry_count,
            previous_snapshot_id=previous.id if previous is not None else None,
            gap_count=gap_count,
        )

    def _snapshot_view(
        self, snapshot: HotlistSnapshot, *, owner_id: UUID, cursor: int | None, limit: int
    ) -> HotlistSnapshotView:
        previous = self._previous(snapshot)
        summary = self._summary(snapshot, previous)
        previous_ranks: dict[str, int] = {}
        if previous is not None:
            for row in self._session.scalars(
                select(HotlistEntryRecord)
                .where(HotlistEntryRecord.snapshot_id == previous.id)
                .order_by(HotlistEntryRecord.rank)
            ):
                previous_ranks.setdefault(_rank_identity(row.url), row.rank)
        query = select(HotlistEntryRecord).where(
            HotlistEntryRecord.owner_id == owner_id,
            HotlistEntryRecord.snapshot_id == snapshot.id,
        )
        if cursor is not None:
            query = query.where(HotlistEntryRecord.rank > cursor)
        entries = self._session.scalars(
            query.order_by(HotlistEntryRecord.rank).limit(limit + 1)
        ).all()
        selected = entries[:limit]
        item_views = tuple(
            HotlistEntryView(
                rank=item.rank,
                title=item.title,
                url=item.url,
                summary=item.summary,
                heat=item.heat,
                published_at=item.published_at,
                content_id=item.content_id,
                previous_rank=previous_ranks.get(_rank_identity(item.url)),
                rank_delta=(
                    previous_ranks[_rank_identity(item.url)] - item.rank
                    if _rank_identity(item.url) in previous_ranks
                    else None
                ),
                rank_change=rank_change(item.rank, previous_ranks.get(_rank_identity(item.url))),
                matched=bool(item.matched_topic_names),
                matched_topic_names=tuple(item.matched_topic_names),
            )
            for item in selected
        )
        return HotlistSnapshotView(
            snapshot_id=snapshot.id,
            source_key=snapshot.source_key,
            observed_at=snapshot.observed_at,
            due_at=summary.due_at,
            operation_id=snapshot.operation_id,
            entry_count=snapshot.entry_count,
            previous_snapshot_id=summary.previous_snapshot_id,
            gap_count=summary.gap_count,
            items=item_views,
            next_cursor=selected[-1].rank if len(entries) > limit else None,
        )
