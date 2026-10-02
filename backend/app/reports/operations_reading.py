"""Current licensed daily-edition health for the operations caller's transaction."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from reports.edition_models import ReportEdition
from reports.edition_reading import load_current_edition_in_transaction
from reports.edition_rules import BEIJING


@dataclass(frozen=True)
class DailyEditionHealth:
    expected_key: str
    due: bool
    current_complete: bool
    status: str | None
    failure_code: str | None
    last_updated_at: datetime | None


def load_daily_edition_health_in_transaction(
    session: Session, *, owner_id: UUID, now: datetime
) -> DailyEditionHealth:
    if not session.in_transaction() or now.utcoffset() is None:
        raise ValueError("daily-edition health requires an aware caller transaction")
    local = now.astimezone(BEIJING)
    expected = (local.date() - timedelta(days=1)).isoformat()
    latest = session.scalar(
        select(ReportEdition)
        .where(
            ReportEdition.owner_id == owner_id,
            ReportEdition.kind == "daily",
            ReportEdition.period_key == expected,
            ReportEdition.created_at <= now,
        )
        .order_by(ReportEdition.revision.desc())
        .limit(1)
    )
    current = load_current_edition_in_transaction(
        session, owner_id=owner_id, kind="daily", key=expected, now=now
    )
    return DailyEditionHealth(
        expected_key=expected,
        due=local.hour >= 10,
        current_complete=current is not None,
        status=latest.status if latest else None,
        failure_code=latest.failure_code if latest else None,
        last_updated_at=latest.updated_at.astimezone(UTC) if latest else None,
    )
