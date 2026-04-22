from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from backend.core.application.protocols import (
    HotspotEventRepository,
    KeywordRuleRepository,
    MonitoredAccountRepository,
    SourceConfigRepository,
)
from backend.core.domain.hotspot_rules import cluster_raw_content
from backend.core.domain.models import HotspotEvent, KeywordRule, MonitoredAccount, RawContentItem, SourceConfig


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
