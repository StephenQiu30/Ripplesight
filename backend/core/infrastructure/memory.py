from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

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


class InMemorySourceConfigRepository:
    def __init__(self, items: Sequence[SourceConfig] | None = None) -> None:
        self._items = {item.id: item for item in items or ()}

    def list_all(self) -> Sequence[SourceConfig]:
        return tuple(self._items.values())

    def get_by_id(self, source_id: str) -> SourceConfig:
        try:
            return self._items[source_id]
        except KeyError as error:
            raise KeyError(f"Unknown source config: {source_id}") from error


class InMemoryKeywordRuleRepository:
    def __init__(self, items: Sequence[KeywordRule] | None = None) -> None:
        self._items = tuple(items or ())

    def list_all(self) -> Sequence[KeywordRule]:
        return self._items


class InMemoryMonitoredAccountRepository:
    def __init__(self, items: Sequence[MonitoredAccount] | None = None) -> None:
        self._items = tuple(items or ())

    def list_all(self) -> Sequence[MonitoredAccount]:
        return self._items


class InMemoryHotspotEventRepository:
    def __init__(self, items: Sequence[HotspotEvent] | None = None) -> None:
        self._items = list(items or ())

    def list_all(self) -> Sequence[HotspotEvent]:
        return tuple(self._items)

    def save_all(self, events: Sequence[HotspotEvent]) -> None:
        self._items = list(events)


class InMemoryRawContentItemRepository:
    def __init__(self, items: Sequence[RawContentItem] | None = None) -> None:
        self._items = list(items or ())

    def list_all(self) -> Sequence[RawContentItem]:
        return tuple(self._items)

    def save_all(self, items: Sequence[RawContentItem]) -> None:
        self._items = list(items)


class InMemoryDailyDigestRepository:
    def __init__(self, items: Sequence[DailyDigest] | None = None) -> None:
        self._items = {item.digest_date.isoformat(): item for item in items or ()}

    def get_by_date(self, digest_date: str) -> DailyDigest | None:
        return self._items.get(digest_date)

    def save(self, digest: DailyDigest) -> DailyDigest:
        self._items[digest.digest_date.isoformat()] = digest
        return digest


class InMemoryFeedbackRepository:
    def __init__(self, items: Sequence[FeedbackRecord] | None = None) -> None:
        self._items = list(items or ())

    def create(self, feedback: FeedbackRecord) -> FeedbackRecord:
        self._items.append(feedback)
        return feedback

    def list_all(self) -> Sequence[FeedbackRecord]:
        return tuple(self._items)


class InMemoryDigestDeliveryGateway:
    def __init__(self, should_fail: bool = False) -> None:
        self._should_fail = should_fail
        self.sent_emails: list[RenderedDigestEmail] = []

    def send(self, email: RenderedDigestEmail) -> DeliveryReceipt:
        if self._should_fail:
            raise RuntimeError("Simulated delivery failure")
        self.sent_emails.append(email)
        return DeliveryReceipt(
            message_id=f"msg-{uuid4().hex[:12]}",
            status="delivered",
            delivered_at=datetime.now(tz=UTC),
        )
