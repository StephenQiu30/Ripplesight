from datetime import datetime, timedelta
from uuid import UUID, uuid5

from sqlalchemy.orm import Session

from monitors.codex_notification import read_codex_notification_in_transaction
from monitors.codex_schemas import NotificationIntent
from notifications.schemas import NotificationSubjectKind, NotificationSubjectMaterial
from publication.notification_reading import load_selected_notification_candidate_in_transaction


def load_notification_material_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    kind: NotificationSubjectKind,
    subject_id: UUID,
    revision: int,
    locator: dict[str, object],
    now: datetime,
) -> NotificationSubjectMaterial | None:
    if not session.in_transaction():
        raise RuntimeError("notification materials require caller transaction")
    if kind == "alert":
        from notifications.alert_services import load_alert_notification_in_transaction

        return load_alert_notification_in_transaction(
            session, owner_id=owner_id, evaluation_id=subject_id, revision=revision, now=now
        )
    if kind == "selected":
        candidate = load_selected_notification_candidate_in_transaction(
            session,
            owner_id=owner_id,
            content_id=subject_id,
            publication_revision=revision,
            now=now,
        )
        if candidate is None or candidate.silent:
            return None
        return NotificationSubjectMaterial(
            kind=kind,
            subject_id=subject_id,
            revision=revision,
            dedupe_key=candidate.dedupe_key,
            occurred_at=candidate.selected_at,
            fingerprint=candidate.fingerprint,
            title=candidate.title,
            text=candidate.summary,
            reading_url=candidate.reading_url,
            expires_at=candidate.selected_at + timedelta(hours=24),
        )
    if kind == "codex_reset":
        try:
            monitor_id = UUID(str(locator["monitor_id"]))
            intent = NotificationIntent.model_validate(locator["intent"])
        except (KeyError, ValueError):
            return None
        if uuid5(monitor_id, intent.event_id) != subject_id:
            return None
        material = read_codex_notification_in_transaction(
            session, owner_id=owner_id, monitor_id=monitor_id, intent=intent, now=now
        )
        if material is None or material.event.revision != revision:
            return None
        labels = {"announce": "预告", "confirm": "已确认", "amend": "更新", "withdraw": "撤回"}
        return NotificationSubjectMaterial(
            kind=kind,
            subject_id=subject_id,
            revision=revision,
            dedupe_key=intent.dedupe_key,
            occurred_at=intent.content_at,
            fingerprint=material.sha256,
            title=f"Codex 额度公告 · {labels[intent.action]}",
            text=material.post.translation_zh or material.post.text,
            reading_url="/codex-resets",
            expires_at=intent.content_at + timedelta(hours=36),
            locator=locator,
        )
    if kind == "report":
        from reports.notification_reading import load_notification_report_in_transaction

        report = load_notification_report_in_transaction(
            session, owner_id=owner_id, report_id=subject_id, version=revision, now=now
        )
        if report is None:
            return None
        return NotificationSubjectMaterial(
            kind=kind,
            subject_id=subject_id,
            revision=revision,
            dedupe_key=f"report:{report.report_id}",
            occurred_at=report.created_at,
            fingerprint=report.fingerprint,
            title=report.title,
            text=report.body_markdown,
            reading_url=f"/reports/{subject_id}",
            locator=locator,
        )
    from reports.notification_reading import load_notification_edition_in_transaction

    edition = load_notification_edition_in_transaction(
        session, owner_id=owner_id, edition_id=subject_id, revision=revision, now=now
    )
    if edition is None:
        return None
    return NotificationSubjectMaterial(
        kind=kind,
        subject_id=subject_id,
        revision=revision,
        dedupe_key=f"edition:{edition.kind}:{edition.key}",
        occurred_at=edition.created_at,
        fingerprint=edition.fingerprint,
        title=edition.title,
        text=edition.body_markdown,
        reading_url=f"/editions/{subject_id}",
    )
