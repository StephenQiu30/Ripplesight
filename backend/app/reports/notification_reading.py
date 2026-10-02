"""Read exact first-final reports and editions; recheck all lineage before each send."""

import hashlib
import json
from datetime import datetime
from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.orm import Session, aliased

from analysis.reads import report_annotations_readable_in_transaction
from content.report_reading import report_inputs_readable_in_transaction
from reports.edition_models import ReportEdition
from reports.edition_services import EditionService
from reports.models import Report
from reports.notification_schemas import (
    NotificationEditionPage,
    NotificationEditionView,
    NotificationReportPage,
    NotificationReportView,
)
from reports.schemas import DailyReportData, ReportInputManifest


def _require(session: Session, now: datetime) -> None:
    if not session.in_transaction() or now.utcoffset() is None:
        raise ValueError("notification report reads require an aware caller transaction")


def _fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def load_notification_report_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    report_id: UUID,
    version: int,
    now: datetime,
) -> NotificationReportView | None:
    _require(session, now)
    record = session.scalar(
        select(Report).where(
            Report.owner_id == owner_id,
            Report.id == report_id,
            Report.version == version,
            Report.status == "final",
        )
    )
    if record is None or record.created_at > now:
        return None
    manifest = ReportInputManifest.model_validate(record.input_manifest)
    if not report_inputs_readable_in_transaction(
        session,
        owner_id=owner_id,
        content_version_ids=manifest.content_version_ids + manifest.comment_content_version_ids,
        observation_ids=manifest.observation_ids,
        now=now,
    ) or not report_annotations_readable_in_transaction(
        session,
        owner_id=owner_id,
        topic_id=record.topic_id,
        annotation_ids=manifest.annotation_ids,
        content_version_ids=manifest.content_version_ids,
    ):
        return None
    data = DailyReportData.model_validate(record.data)
    frozen = {
        "report_id": str(record.id),
        "version": record.version,
        "topic_id": str(record.topic_id),
        "kind": record.kind,
        "title": f"{data.topic_name} · {record.window_start.date().isoformat()}",
        "body_markdown": record.body_markdown,
        "input_manifest": record.input_manifest,
        "data": record.data,
    }
    return NotificationReportView.model_validate(
        {
            **{
                key: value for key, value in frozen.items() if key not in {"input_manifest", "data"}
            },
            "created_at": record.created_at,
            "fingerprint": _fingerprint(frozen),
        }
    )


def list_first_final_notification_reports_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    enabled_at: datetime,
    now: datetime,
    after_report_id: UUID | None = None,
    limit: int = 100,
) -> NotificationReportPage:
    _require(session, now)
    if enabled_at.utcoffset() is None or enabled_at > now or not 1 <= limit <= 100:
        raise ValueError("invalid notification report scan")
    previous = aliased(Report)
    query = select(Report).where(
        Report.owner_id == owner_id,
        Report.status == "final",
        Report.created_at >= enabled_at,
        Report.created_at <= now,
        ~exists().where(
            previous.owner_id == Report.owner_id,
            previous.topic_id == Report.topic_id,
            previous.kind == Report.kind,
            previous.window_start == Report.window_start,
            previous.status == "final",
            previous.version < Report.version,
        ),
    )
    if after_report_id is not None:
        query = query.where(Report.id > after_report_id)
    rows = list(session.scalars(query.order_by(Report.id).limit(limit + 1)))
    views = [
        load_notification_report_in_transaction(
            session, owner_id=owner_id, report_id=row.id, version=row.version, now=now
        )
        for row in rows[:limit]
    ]
    return NotificationReportPage(
        reports=tuple(view for view in views if view is not None),
        next_after_report_id=rows[limit - 1].id if len(rows) > limit else None,
    )


def load_notification_edition_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    edition_id: UUID,
    revision: int,
    now: datetime,
) -> NotificationEditionView | None:
    _require(session, now)
    record = session.scalar(
        select(ReportEdition).where(
            ReportEdition.owner_id == owner_id,
            ReportEdition.id == edition_id,
            ReportEdition.revision == revision,
            ReportEdition.status == "complete",
        )
    )
    if record is None or record.created_at > now:
        return None
    view = EditionService(session, clock=lambda: now)._view(record)
    if not view.valid or view.historical_revision or not view.title or not view.body_markdown:
        return None
    return NotificationEditionView(
        edition_id=record.id,
        revision=record.revision,
        kind=view.kind,
        key=view.key,
        title=view.title,
        body_markdown=view.body_markdown,
        created_at=record.created_at,
        fingerprint=_fingerprint(
            {
                "id": str(record.id),
                "revision": record.revision,
                "input_fingerprint": record.input_fingerprint,
                "input_snapshot": record.input_snapshot,
                "body_markdown": view.body_markdown,
                "content": record.content,
            }
        ),
    )


def list_first_final_notification_editions_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    enabled_at: datetime,
    now: datetime,
    after_edition_id: UUID | None = None,
    limit: int = 100,
) -> NotificationEditionPage:
    _require(session, now)
    if enabled_at.utcoffset() is None or enabled_at > now or not 1 <= limit <= 100:
        raise ValueError("invalid notification edition scan")
    previous = aliased(ReportEdition)
    query = select(ReportEdition).where(
        ReportEdition.owner_id == owner_id,
        ReportEdition.status == "complete",
        ReportEdition.created_at >= enabled_at,
        ReportEdition.created_at <= now,
        ~exists().where(
            previous.owner_id == ReportEdition.owner_id,
            previous.kind == ReportEdition.kind,
            previous.period_key == ReportEdition.period_key,
            previous.status == "complete",
            previous.revision < ReportEdition.revision,
        ),
    )
    if after_edition_id is not None:
        query = query.where(ReportEdition.id > after_edition_id)
    rows = list(session.scalars(query.order_by(ReportEdition.id).limit(limit + 1)))
    views = [
        load_notification_edition_in_transaction(
            session, owner_id=owner_id, edition_id=row.id, revision=row.revision, now=now
        )
        for row in rows[:limit]
    ]
    return NotificationEditionPage(
        editions=tuple(view for view in views if view is not None),
        next_after_edition_id=rows[limit - 1].id if len(rows) > limit else None,
    )
