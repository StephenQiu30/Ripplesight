from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from backend.core.domain.models import HotspotEvent, KeywordRule, MonitoredAccount, SourceConfig


class SourceConfigRepository(Protocol):
    def list_all(self) -> Sequence[SourceConfig]: ...

    def get_by_id(self, source_id: str) -> SourceConfig: ...


class KeywordRuleRepository(Protocol):
    def list_all(self) -> Sequence[KeywordRule]: ...


class MonitoredAccountRepository(Protocol):
    def list_all(self) -> Sequence[MonitoredAccount]: ...


class HotspotEventRepository(Protocol):
    def list_all(self) -> Sequence[HotspotEvent]: ...

    def save_all(self, events: Sequence[HotspotEvent]) -> None: ...
