"""Domain layer for hotspot detection rules and entities."""
from .hotspot_rules import cluster_raw_content, derive_event_key, rank_hotspot_events, score_hotspot_event
from .models import (
    AccessMethod,
    DailyDigest,
    EvidenceLink,
    FeedbackRecord,
    HotspotEvent,
    KeywordRule,
    MonitoredAccount,
    RawContentItem,
    SourceConfig,
    SourceType,
)

__all__ = [
    "AccessMethod",
    "DailyDigest",
    "EvidenceLink",
    "FeedbackRecord",
    "HotspotEvent",
    "KeywordRule",
    "MonitoredAccount",
    "RawContentItem",
    "SourceConfig",
    "SourceType",
    "cluster_raw_content",
    "derive_event_key",
    "rank_hotspot_events",
    "score_hotspot_event",
]
