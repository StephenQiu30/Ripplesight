from __future__ import annotations

from functools import lru_cache

from backend.core.application import (
    DigestService,
    FeedbackService,
    HotspotDiscoveryService,
    SearchService,
    SourceGovernanceService,
)
from backend.core.infrastructure import (
    InMemoryDailyDigestRepository,
    InMemoryFeedbackRepository,
    InMemoryHotspotEventRepository,
    InMemoryKeywordRuleRepository,
    InMemoryMonitoredAccountRepository,
    InMemorySourceConfigRepository,
)

from .bootstrap import (
    build_keyword_rules,
    build_monitored_accounts,
    build_raw_records,
    build_source_configs,
    default_ingested_at,
)


@lru_cache(maxsize=1)
def get_source_repository() -> InMemorySourceConfigRepository:
    return InMemorySourceConfigRepository(build_source_configs())


@lru_cache(maxsize=1)
def get_governance_service() -> SourceGovernanceService:
    return SourceGovernanceService(
        source_repository=get_source_repository(),
        keyword_rule_repository=InMemoryKeywordRuleRepository(build_keyword_rules()),
        monitored_account_repository=InMemoryMonitoredAccountRepository(build_monitored_accounts()),
    )


@lru_cache(maxsize=1)
def get_hotspot_event_repository() -> InMemoryHotspotEventRepository:
    return InMemoryHotspotEventRepository()


@lru_cache(maxsize=1)
def get_hotspot_service() -> HotspotDiscoveryService:
    repository = get_hotspot_event_repository()
    service = HotspotDiscoveryService(
        source_repository=get_source_repository(),
        hotspot_event_repository=repository,
    )
    raw_items = []
    ingested_at = default_ingested_at()
    for source_id, records in build_raw_records().items():
        raw_items.extend(service.normalize_items(source_id, records, ingested_at=ingested_at))
    service.build_hotspot_events(raw_items)
    return service


def get_initialized_hotspot_event_repository() -> InMemoryHotspotEventRepository:
    get_hotspot_service()
    return get_hotspot_event_repository()


@lru_cache(maxsize=1)
def get_daily_digest_repository() -> InMemoryDailyDigestRepository:
    return InMemoryDailyDigestRepository()


@lru_cache(maxsize=1)
def get_feedback_repository() -> InMemoryFeedbackRepository:
    return InMemoryFeedbackRepository()


@lru_cache(maxsize=1)
def get_digest_service() -> DigestService:
    return DigestService(
        hotspot_event_repository=get_initialized_hotspot_event_repository(),
        daily_digest_repository=get_daily_digest_repository(),
    )


@lru_cache(maxsize=1)
def get_search_service() -> SearchService:
    return SearchService(get_initialized_hotspot_event_repository())


@lru_cache(maxsize=1)
def get_feedback_service() -> FeedbackService:
    return FeedbackService(get_feedback_repository())
