"""Frozen, permission-checked report materials for explicit outbound subscriptions."""

from datetime import datetime
from uuid import UUID

from core.schemas import OutputModel
from reports.edition_rules import EditionKind
from reports.schemas import ReportKind


class NotificationReportView(OutputModel):
    report_id: UUID
    version: int
    topic_id: UUID
    kind: ReportKind
    title: str
    body_markdown: str
    created_at: datetime
    fingerprint: str


class NotificationReportPage(OutputModel):
    reports: tuple[NotificationReportView, ...]
    next_after_report_id: UUID | None


class NotificationEditionView(OutputModel):
    edition_id: UUID
    revision: int
    kind: EditionKind
    key: str
    title: str
    body_markdown: str
    created_at: datetime
    fingerprint: str


class NotificationEditionPage(OutputModel):
    editions: tuple[NotificationEditionView, ...]
    next_after_edition_id: UUID | None
