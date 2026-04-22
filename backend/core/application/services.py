from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, date, datetime
from uuid import uuid4
from typing import Any

from backend.core.application.protocols import (
    DailyDigestRepository,
    FeedbackRepository,
    HotspotEventRepository,
    KeywordRuleRepository,
    MonitoredAccountRepository,
    SourceConfigRepository,
)
from backend.core.domain.hotspot_rules import cluster_raw_content
from backend.core.domain.models import (
    DailyDigest,
    FeedbackRecord,
    HotspotEvent,
    KeywordRule,
    MonitoredAccount,
    RawContentItem,
    SourceConfig,
)


class SourceGovernanceService:
    def __init__(
        self,
        source_repository: SourceConfigRepository,
        keyword_rule_repository: KeywordRuleRepository,
        monitored_account_repository: MonitoredAccountRepository,
    ) -> None:
        self._source_repository = source_repository
        self._keyword_rule_repository = keyword_rule_repository
        self._monitored_account_repository = monitored_account_repository

    def list_sources(self, enabled: bool | None = None) -> list[SourceConfig]:
        return _filter_enabled(self._source_repository.list_all(), enabled)

    def list_keyword_rules(self, enabled: bool | None = True) -> list[KeywordRule]:
        return _filter_enabled(self._keyword_rule_repository.list_all(), enabled)

    def list_monitored_accounts(self, enabled: bool | None = True) -> list[MonitoredAccount]:
        return _filter_enabled(self._monitored_account_repository.list_all(), enabled)


class HotspotDiscoveryService:
    def __init__(
        self,
        source_repository: SourceConfigRepository,
        hotspot_event_repository: HotspotEventRepository | None = None,
    ) -> None:
        self._source_repository = source_repository
        self._hotspot_event_repository = hotspot_event_repository

    def normalize_items(
        self,
        source_id: str,
        records: Iterable[Mapping[str, Any]],
        *,
        ingested_at: datetime | None = None,
    ) -> list[RawContentItem]:
        source = self._source_repository.get_by_id(source_id)
        normalized: list[RawContentItem] = []
        ingestion_time = ingested_at or datetime.now(tz=UTC)
        for index, record in enumerate(records, start=1):
            normalized.append(
                RawContentItem(
                    id=f"{source.id}:{record.get('external_id', index)}",
                    source_config_id=source.id,
                    source_name=source.name,
                    source_type=source.source_type,
                    external_id=str(record.get("external_id", index)),
                    title=str(record.get("title", "")).strip() or "Untitled",
                    content_excerpt=str(record.get("content_excerpt", "")).strip(),
                    url=str(record.get("url", "")).strip(),
                    author=str(record.get("author", "")).strip(),
                    published_at=_coerce_datetime(record.get("published_at"), fallback=ingestion_time),
                    language=str(record.get("language", source.language)).strip() or source.language,
                    raw_payload=dict(record.get("raw_payload", record)),
                    ingested_at=ingestion_time,
                )
            )
        return normalized

    def build_hotspot_events(self, items: Sequence[RawContentItem]) -> list[HotspotEvent]:
        events = cluster_raw_content(items)
        if self._hotspot_event_repository is not None:
            self._hotspot_event_repository.save_all(events)
        return events


class DigestService:
    def __init__(
        self,
        hotspot_event_repository: HotspotEventRepository,
        daily_digest_repository: DailyDigestRepository,
    ) -> None:
        self._hotspot_event_repository = hotspot_event_repository
        self._daily_digest_repository = daily_digest_repository

    def get_today_digest(self, *, today: date | None = None, generated_at: datetime | None = None) -> DailyDigest:
        digest_date = today or datetime.now(tz=UTC).date()
        cached = self._daily_digest_repository.get_by_date(digest_date.isoformat())
        if cached is not None:
            return cached

        events = list(self._hotspot_event_repository.list_all())
        highlights = tuple(event.event_title for event in events[:3])
        digest = DailyDigest(
            id=f"digest-{digest_date.isoformat()}",
            digest_date=digest_date,
            title=f"AI 热点日报 {digest_date.isoformat()}",
            highlights=highlights,
            event_ids=tuple(event.id for event in events[:5]),
            generated_at=generated_at or datetime.now(tz=UTC),
            delivery_status="assembled",
        )
        return self._daily_digest_repository.save(digest)


class SearchService:
    def __init__(self, hotspot_event_repository: HotspotEventRepository) -> None:
        self._hotspot_event_repository = hotspot_event_repository

    def search_events(self, query: str) -> list[HotspotEvent]:
        needle = query.strip().casefold()
        if not needle:
            return []
        matches = []
        for event in self._hotspot_event_repository.list_all():
            summary = (event.summary_zh or event.event_title).casefold()
            if needle in event.event_title.casefold() or needle in summary:
                matches.append(event)
        return matches


class FeedbackService:
    def __init__(self, feedback_repository: FeedbackRepository) -> None:
        self._feedback_repository = feedback_repository

    def submit_feedback(
        self,
        *,
        target_type: str,
        target_id: str,
        feedback_type: str,
        comment: str | None = None,
        created_at: datetime | None = None,
    ) -> FeedbackRecord:
        feedback = FeedbackRecord(
            id=f"feedback-{uuid4().hex[:12]}",
            target_type=target_type,
            target_id=target_id,
            feedback_type=feedback_type,
            comment=comment,
            created_at=created_at or datetime.now(tz=UTC),
        )
        return self._feedback_repository.create(feedback)


def _filter_enabled(items: Sequence[Any], enabled: bool | None) -> list[Any]:
    if enabled is None:
        return list(items)
    return [item for item in items if item.enabled is enabled]


def _coerce_datetime(value: Any, *, fallback: datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return fallback
