"""Freeze trustworthy identity history without keeping deleted object keys."""

import hashlib
from datetime import datetime
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from content.models import ContentIdentityHistory


def register_new_owner_history_in_transaction(
    session: Session, *, owner_id: UUID, now: datetime
) -> None:
    """Register only a genuinely new account in its creation transaction.

    Existing history, including unknown state, is never reset by this operation.
    Caller must have just inserted the unique new account; legacy imports are excluded.
    """
    if not session.in_transaction() or now.utcoffset() is None:
        raise ValueError("history registration requires an aware account transaction")
    session.execute(
        insert(ContentIdentityHistory)
        .values(owner_id=owner_id, state="complete", registered_at=now, invalidated_at=None)
        .on_conflict_do_nothing(index_elements=["owner_id"])
    )


def lock_owner_history_in_transaction(
    session: Session, *, owner_id: UUID
) -> ContentIdentityHistory | None:
    """Serialize ingestion and complete cleanup before identity or native-key locks.

    Missing registration is unknown, never a new clean history. The advisory lock
    also covers legacy accounts without a registration row.
    """
    if not session.in_transaction():
        raise ValueError("history lock requires a caller transaction")
    key = int.from_bytes(
        hashlib.sha256(b"content-history-v1" + owner_id.bytes).digest()[:8], "big", signed=True
    )
    session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
    return session.scalar(
        select(ContentIdentityHistory)
        .where(ContentIdentityHistory.owner_id == owner_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
