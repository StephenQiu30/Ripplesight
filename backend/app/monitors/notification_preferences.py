from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from monitors.models import MonitorTopic


def load_topic_notification_target_names_in_transaction(
    session: Session, *, owner_id: UUID, topic_ids: tuple[UUID, ...]
) -> dict[UUID, tuple[str, ...]]:
    if not session.in_transaction() or len(topic_ids) > 1000:
        raise RuntimeError("topic notification preferences require a bounded caller transaction")
    if not topic_ids:
        return {}
    return {
        topic_id: tuple(names)
        for topic_id, names in session.execute(
            select(MonitorTopic.id, MonitorTopic.notification_target_names).where(
                MonitorTopic.owner_id == owner_id, MonitorTopic.id.in_(topic_ids)
            )
        )
    }
