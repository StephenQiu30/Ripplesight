from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import replace
from datetime import UTC, date, datetime
from uuid import uuid4
from typing import Any

from backend.core.application.protocols import (
    DailyDigestRepository,
    DigestDeliveryGateway,
    FeedbackRepository,
    HotspotEventRepository,
    RawContentItemRepository,
    KeywordRuleRepository,
    MonitoredAccountRepository,
    SourceConfigRepository,
)
from backend.core.domain.hotspot_rules import cluster_raw_content
from backend.core.domain.models import (
    DailyDigest,
    DeliveryReceipt,
    FeedbackRecord,
    HotspotEvent,
    KeywordRule,
    MonitoredAccount,
    RawContentItem,
    RenderedDigestEmail,
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
        raw_content_repository: RawContentItemRepository | None = None,
    ) -> None:
        self._source_repository = source_repository
        self._hotspot_event_repository = hotspot_event_repository
        self._raw_content_repository = raw_content_repository

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

    def collect_raw_items(
        self,
        records_by_source: Mapping[str, Iterable[Mapping[str, Any]]],
        *,
        ingested_at: datetime | None = None,
    ) -> list[RawContentItem]:
        active_sources = {item.id: item for item in self._source_repository.list_all() if item.enabled}
        collected: list[RawContentItem] = []
        for source_id, records in records_by_source.items():
            if source_id not in active_sources:
                continue
            try:
                normalized = self.normalize_items(source_id, records, ingested_at=ingested_at)
            except Exception:
                # Downstream discovery should degrade on source-level failures
                # and continue with available sources.
                continue
            collected.extend(normalized)

        if self._raw_content_repository is not None:
            self._raw_content_repository.save_all(collected)
        return collected

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


class DigestRenderService:
    def __init__(self, hotspot_event_repository: HotspotEventRepository) -> None:
        self._hotspot_event_repository = hotspot_event_repository

    def render_digest_email(self, digest: DailyDigest, *, recipient: str) -> RenderedDigestEmail:
        events = {event.id: event for event in self._hotspot_event_repository.list_all()}
        lines = [digest.title, "", "今日摘要："]
        for index, highlight in enumerate(digest.highlights, start=1):
            lines.append(f"{index}. {highlight}")
        if digest.event_ids:
            lines.append("")
            lines.append("事件详情：")
        for event_id in digest.event_ids:
            event = events.get(event_id)
            if event is None:
                continue
            lines.append(f"- {event.event_title} | score={event.score}")
        return RenderedDigestEmail(
            digest_id=digest.id,
            digest_date=digest.digest_date,
            recipient=recipient,
            subject=f"[AI Hotspot Radar] {digest.title}",
            body="\n".join(lines),
        )


class DigestDeliveryWorkflowService:
    def __init__(
        self,
        digest_service: DigestService,
        digest_repository: DailyDigestRepository,
        digest_render_service: DigestRenderService,
        delivery_gateway: DigestDeliveryGateway,
    ) -> None:
        self._digest_service = digest_service
        self._digest_repository = digest_repository
        self._digest_render_service = digest_render_service
        self._delivery_gateway = delivery_gateway

    def generate_and_deliver(self, *, recipient: str, today: date | None = None) -> tuple[DailyDigest, DeliveryReceipt]:
        digest = self._digest_service.get_today_digest(today=today)
        rendered = self._digest_render_service.render_digest_email(digest, recipient=recipient)
        try:
            receipt = self._delivery_gateway.send(rendered)
        except Exception:
            failed = replace(digest, delivery_status="failed")
            self._digest_repository.save(failed)
            raise
        delivered = replace(digest, delivery_status=receipt.status)
        self._digest_repository.save(delivered)
        return delivered, receipt


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
