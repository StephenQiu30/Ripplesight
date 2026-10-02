from __future__ import annotations

from uuid import UUID

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from core.errors import ApplicationError
from db.metadata import metadata


def require_owner_id(session: Session, owner_id: UUID) -> UUID:
    """Explicit maintenance targets must name a real account; never choose the first owner."""
    table = metadata.tables["identity_users"]
    bind = session.get_bind()
    engine = bind if isinstance(bind, Engine) else bind.engine
    with engine.connect() as connection:
        exists = connection.scalar(select(table.c.id).where(table.c.id == owner_id))
    if exists is None:
        raise ApplicationError("resource_not_found")
    return owner_id


def list_owner_ids_in_transaction(session: Session) -> tuple[UUID, ...]:
    if not session.in_transaction():
        raise RuntimeError("account enumeration requires the caller's transaction")
    table = metadata.tables["identity_users"]
    return tuple(session.scalars(select(table.c.id).order_by(table.c.id)))
