from datetime import datetime
from typing import Literal

from core.schemas import OutputModel
from publication.schemas import PublicItemView


class PublicTopicSummaryView(OutputModel):
    slug: str
    name: str
    group: Literal["company", "field", "genre"]
    definition: str
    total: int
    recent: int
    indexable: bool
    latest_at: datetime | None


class PublicTopicDirectoryView(OutputModel):
    topics: list[PublicTopicSummaryView]
    refresh_at: datetime | None


class PublicRelatedTopicView(OutputModel):
    slug: str
    name: str


class PublicTopicPageView(OutputModel):
    topic: PublicTopicSummaryView
    related: list[PublicRelatedTopicView]
    items: list[PublicItemView]
    page: int
    page_count: int
    refresh_at: datetime | None
