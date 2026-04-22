from __future__ import annotations

from collections.abc import Sequence

from backend.core.domain.models import HotspotEvent, KeywordRule, MonitoredAccount, SourceConfig


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
