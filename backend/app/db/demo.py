from __future__ import annotations

from uuid import UUID

from sqlalchemy import Engine, inspect, select, union
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from core.errors import ApplicationError, DependencyUnavailableError
from db.metadata import metadata

DEFAULT_DEMO_SCOPE_ID = UUID("00000000-0000-4000-8000-000000000001")


def resolve_demo_scope(session: Session) -> UUID:
    """Resolve the sole business partition without starting a caller transaction."""
    bind = session.get_bind()
    engine = bind if isinstance(bind, Engine) else bind.engine
    partition_queries = [
        select(table.c.owner_id).distinct().limit(2).subquery()
        for table in metadata.tables.values()
        if "owner_id" in table.c
    ]
    partitions = union(*(select(query.c.owner_id) for query in partition_queries)).limit(2)
    try:
        with engine.connect() as connection:
            scope_ids = connection.execute(partitions).scalars().all()
            if len(scope_ids) > 1:
                raise DependencyUnavailableError("demo_scope_conflict")
            if scope_ids:
                return UUID(str(scope_ids[0]))

            # Empty legacy schemas may enforce identity foreign keys even without users.
            # Their version must be rebuilt separately rather than create a fake account.
            if inspect(connection).has_table("identity_users"):
                raise DependencyUnavailableError("demo_scope_conflict")
            return DEFAULT_DEMO_SCOPE_ID
    except SQLAlchemyError as error:
        raise DependencyUnavailableError() from error


def require_demo_partition_match(scope_id: UUID, resource_scope_id: UUID) -> None:
    """Reject a historical resource that belongs to another business partition."""
    if scope_id != resource_scope_id:
        raise ApplicationError("resource_not_found")
