from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Generic, TypeVar

from backend.core.domain.models import SourceType

T = TypeVar("T")


def _validate_page(value: int, field_name: str) -> None:
    if value < 1:
        raise ValueError(f"{field_name} must be greater than or equal to 1")


@dataclass(frozen=True, slots=True)
class PageMeta:
    page: int = 1
    page_size: int = 20
    total: int = 0

    def __post_init__(self) -> None:
        _validate_page(self.page, "page")
        _validate_page(self.page_size, "page_size")
        if self.page_size > 100:
            raise ValueError("page_size must be less than or equal to 100")
        if self.total < 0:
            raise ValueError("total must be greater than or equal to 0")


@dataclass(frozen=True, slots=True)
class PaginatedResult(Generic[T]):
    items: tuple[T, ...]
    meta: PageMeta


@dataclass(frozen=True, slots=True)
class SourceListQuery:
    page: int = 1
    page_size: int = 20
    enabled: bool | None = None

    def __post_init__(self) -> None:
        _validate_page(self.page, "page")
        _validate_page(self.page_size, "page_size")


@dataclass(frozen=True, slots=True)
class EventListQuery:
    page: int = 1
    page_size: int = 20
    topic: str | None = None
    source_type: SourceType | None = None
    from_date: date | None = None
    to_date: date | None = None

    def __post_init__(self) -> None:
        _validate_page(self.page, "page")
        _validate_page(self.page_size, "page_size")


@dataclass(frozen=True, slots=True)
class SearchQuery:
    q: str
    page: int = 1
    page_size: int = 20

    def __post_init__(self) -> None:
        if not self.q.strip():
            raise ValueError("q must not be empty")
        _validate_page(self.page, "page")
        _validate_page(self.page_size, "page_size")
