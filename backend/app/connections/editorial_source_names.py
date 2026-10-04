"""Owner-scoped human source labels; identity and all collector configuration stay private."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from connections.editorial_models import EditorialSourceProfile


def load_editorial_source_names_in_transaction(
    session: Session, *, owner_id: UUID, source_keys: tuple[str, ...]
) -> dict[str, str]:
    if not session.in_transaction():
        raise RuntimeError("source name reads require caller transaction")
    return {
        source_key: name
        for source_key, name in session.execute(
            select(EditorialSourceProfile.source_key, EditorialSourceProfile.name).where(
                EditorialSourceProfile.owner_id == owner_id,
                EditorialSourceProfile.source_key.in_(source_keys),
            )
        )
    }
