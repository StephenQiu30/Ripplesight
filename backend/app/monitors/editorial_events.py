"""Internal event partition; it has no collection/report schedule or public topic lifecycle."""

from datetime import datetime, time
from uuid import UUID, uuid5

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from core.errors import ApplicationError
from monitors.models import MonitorTopic, MonitorTopicVersion

_NAMESPACE = UUID("2a3b5b69-b29b-4f06-bb46-76f664931e53")


def editorial_event_topic_id(owner_id: UUID) -> UUID:
    return uuid5(_NAMESPACE, f"{owner_id}:editorial-events")


def reject_internal_editorial_topic(*, owner_id: UUID, topic_id: UUID) -> None:
    if topic_id == editorial_event_topic_id(owner_id):
        raise ApplicationError("resource_not_found")


def ensure_editorial_event_topic_in_transaction(
    session: Session, *, owner_id: UUID, now: datetime
) -> UUID:
    if not session.in_transaction() or now.utcoffset() is None:
        raise ValueError("editorial partition requires an aware caller transaction")
    identity = editorial_event_topic_id(owner_id)
    session.execute(
        insert(MonitorTopic)
        .values(
            id=identity,
            owner_id=owner_id,
            name="全站事件",
            status="paused",
            readiness_status="ready",
            current_version=1,
            collection_interval_seconds=1800,
            report_time=time(9),
            report_timezone="Asia/Shanghai",
            weekly_report_enabled=False,
            notification_target_names=[],
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_nothing(index_elements=[MonitorTopic.id])
    )
    session.execute(
        insert(MonitorTopicVersion)
        .values(
            topic_id=identity,
            version=1,
            created_by=owner_id,
            match_any=["editorial-input"],
            match_all=[],
            exclude=[],
            source_keys=[],
            collection_interval_seconds=1800,
            created_at=now,
        )
        .on_conflict_do_nothing(
            index_elements=[MonitorTopicVersion.topic_id, MonitorTopicVersion.version]
        )
    )
    return identity
