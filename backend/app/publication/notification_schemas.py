"""Summary-only outbound contracts; no ORM, source bodies or channel credentials."""

from datetime import datetime
from uuid import UUID

from core.schemas import OutputModel
from publication.schemas import FrozenPublicationReference


class SelectedNotificationCandidate(FrozenPublicationReference):
    selected_at: datetime
    title: str
    summary: str
    reading_url: str
    source_name: str
    dedupe_key: str
    silent: bool = False
    fingerprint: str


class SelectedNotificationPage(OutputModel):
    candidates: tuple[SelectedNotificationCandidate, ...]
    next_after_content_id: UUID | None


class WeeklySelectedSourceCount(OutputModel):
    source_key: str
    current_count: int
    previous_count: int
