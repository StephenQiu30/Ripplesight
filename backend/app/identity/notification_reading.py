"""Only an account's verified binding may receive self-service report mail."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from identity.models import IdentityUser


def load_bound_notification_email_in_transaction(session: Session, *, owner_id: UUID) -> str | None:
    if not session.in_transaction():
        raise RuntimeError("bound email reading requires caller transaction")
    return session.scalar(select(IdentityUser.email).where(IdentityUser.id == owner_id))
