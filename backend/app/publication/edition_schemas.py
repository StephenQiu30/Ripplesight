"""Public calendar and navigation describe only currently readable fixed editions."""

from datetime import datetime
from typing import Literal

from core.schemas import OutputModel

EditionKind = Literal["daily", "weekly", "monthly"]


class PublicEditionIndexView(OutputModel):
    kind: EditionKind
    key: str
    title: str
    revision: int
    created_at: datetime
    reading_url: str
    indexable: bool = False


class PublicEditionCatalogueView(OutputModel):
    kind: EditionKind
    entries: list[PublicEditionIndexView]
    next_before_key: str | None


class PublicEditionNavigationView(OutputModel):
    current: PublicEditionIndexView | None
    previous: PublicEditionIndexView | None
    next: PublicEditionIndexView | None


class PublicDailyCalendarView(OutputModel):
    month: str
    entries: list[PublicEditionIndexView]
