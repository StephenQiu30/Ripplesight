"""Reject duplicate local RSSHub targets without changing any source grants."""

from __future__ import annotations

from hashlib import sha256
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from connections.editorial_models import EditorialSourceProfile, EditorialSourceVersion
from core.errors import ApplicationError
from sources.editorial_schemas import EditorialSourceConfiguration


def require_unique_rsshub_target_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    configuration: EditorialSourceConfiguration,
    profile_id: UUID | None = None,
) -> None:
    if not session.in_transaction():
        raise RuntimeError("source target deduplication requires caller transaction")
    rsshub = configuration.rsshub
    if configuration.kind != "rss" or rsshub is None:
        return
    # Local hostname, output bounds, review and revision do not create another
    # subscription target. The caller should edit the existing profile instead.
    identity = (str(owner_id), rsshub.platform, rsshub.route, rsshub.target)
    digest = sha256(b"rsshub-target:" + repr(identity).encode()).digest()
    lock_key = int.from_bytes(digest[:8], byteorder="big", signed=True)
    session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})
    current = EditorialSourceVersion.configuration["rsshub"]
    query = (
        select(EditorialSourceProfile.id)
        .join(
            EditorialSourceVersion,
            (EditorialSourceVersion.owner_id == EditorialSourceProfile.owner_id)
            & (EditorialSourceVersion.profile_id == EditorialSourceProfile.id)
            & (EditorialSourceVersion.version == EditorialSourceProfile.current_version),
        )
        .where(
            EditorialSourceProfile.owner_id == owner_id,
            EditorialSourceVersion.kind == "rss",
            current["platform"].astext == rsshub.platform,
            current["route"].astext == rsshub.route,
            current["target"].astext == rsshub.target,
        )
        .limit(1)
    )
    if profile_id is not None:
        query = query.where(EditorialSourceProfile.id != profile_id)
    if session.scalar(query) is not None:
        raise ApplicationError("editorial_target_conflict")
