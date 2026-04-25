from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from backend.core.domain.models import (
    DailyDigest,
    DeliveryReceipt,
    FeedbackRecord,
    HotspotEvent,
    RawContentItem,
    KeywordRule,
    MonitoredAccount,
    RenderedDigestEmail,
    SourceConfig,
)


class SourceConfigRepository(Protocol):
    def list_all(self) -> Sequence[SourceConfig]: ...

    def get_by_id(self, source_id: str) -> SourceConfig: ...


class RawContentItemRepository(Protocol):
    def list_all(self) -> Sequence[RawContentItem]: ...

    def save_all(self, items: Sequence[RawContentItem]) -> None: ...


class KeywordRuleRepository(Protocol):
    def list_all(self) -> Sequence[KeywordRule]: ...


class MonitoredAccountRepository(Protocol):
    def list_all(self) -> Sequence[MonitoredAccount]: ...


class HotspotEventRepository(Protocol):
    def list_all(self) -> Sequence[HotspotEvent]: ...

    def save_all(self, events: Sequence[HotspotEvent]) -> None: ...


class DailyDigestRepository(Protocol):
    def get_by_date(self, digest_date: str) -> DailyDigest | None: ...

    def save(self, digest: DailyDigest) -> DailyDigest: ...


class FeedbackRepository(Protocol):
    def create(self, feedback: FeedbackRecord) -> FeedbackRecord: ...

    def list_all(self) -> Sequence[FeedbackRecord]: ...


class DigestDeliveryGateway(Protocol):
    def send(self, email: RenderedDigestEmail) -> DeliveryReceipt: ...
