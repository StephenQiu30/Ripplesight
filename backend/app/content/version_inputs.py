"""Frozen actual-input dependency graph for content versions, using original policy facts."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from content.models import (
    ContentObservation,
    ContentVersion,
    ContentVersionInput,
)
from core.errors import ApplicationError


def observations_readable_in_transaction(
    session: Session, *, owner_id: UUID, observation_ids: tuple[UUID, ...], now: datetime
) -> bool:
    """ALL exact original inputs, using the same bounded bulk read implementation."""
    from content.observation_reading import readable_observation_groups_in_transaction

    return (
        readable_observation_groups_in_transaction(
            session,
            owner_id=owner_id,
            observation_groups={"single": observation_ids},
            now=now,
        )["single"]
        is not None
    )


def save_version_inputs_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    content_version_id: UUID,
    observation_ids: tuple[UUID, ...],
) -> None:
    if not session.in_transaction() or not 1 <= len(observation_ids) <= 32:
        raise ValueError("content inputs require a bounded caller transaction")
    session.flush()
    version = session.scalar(
        select(ContentVersion)
        .where(ContentVersion.owner_id == owner_id, ContentVersion.id == content_version_id)
        .with_for_update()
    )
    inputs = set(observation_ids)
    if version is None or version.owner_id != owner_id or len(inputs) != len(observation_ids):
        raise ApplicationError("editorial_material_unavailable")
    found = set(
        session.scalars(
            select(ContentObservation.id).where(
                ContentObservation.owner_id == owner_id,
                ContentObservation.id.in_(inputs),
                ContentObservation.content_version_id.is_not(None),
            )
        )
    )
    if found != inputs:
        raise ApplicationError("editorial_material_unavailable")
    existing = set(
        session.scalars(
            select(ContentVersionInput.observation_id).where(
                ContentVersionInput.owner_id == owner_id,
                ContentVersionInput.content_version_id == content_version_id,
            )
        )
    )
    if existing and existing != inputs:
        raise ApplicationError("idempotency_conflict")
    for observation_id in sorted(inputs, key=str):
        session.execute(
            insert(ContentVersionInput)
            .values(
                owner_id=owner_id,
                content_version_id=content_version_id,
                observation_id=observation_id,
            )
            .on_conflict_do_nothing()
        )


def version_inputs_readable_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    content_version_ids: tuple[UUID, ...],
    now: datetime,
) -> bool:
    """ALL exact dependency observations, including upstream versions; no alias substitution."""
    if not session.in_transaction() or now.tzinfo is None:
        raise ValueError("version input reads require an aware caller transaction")
    pending = set(content_version_ids)
    visited: set[UUID] = set()
    while pending:
        batch = pending - visited
        if not batch:
            break
        if len(visited) + len(batch) > 2000:
            return False
        found = set(
            session.scalars(
                select(ContentVersion.id).where(
                    ContentVersion.owner_id == owner_id,
                    ContentVersion.id.in_(batch),
                )
            )
        )
        if found != batch:
            return False
        visited.update(batch)
        observations = tuple(
            session.scalars(
                select(ContentVersionInput.observation_id).where(
                    ContentVersionInput.owner_id == owner_id,
                    ContentVersionInput.content_version_id.in_(batch),
                )
            )
        )
        for start in range(0, len(observations), 32):
            items = tuple(sorted(set(observations[start : start + 32]), key=str))
            if items and not observations_readable_in_transaction(
                session,
                owner_id=owner_id,
                observation_ids=items,
                now=now,
            ):
                return False
        pending = {
            value
            for value in session.scalars(
                select(ContentObservation.content_version_id).where(
                    ContentObservation.owner_id == owner_id,
                    ContentObservation.id.in_(observations),
                    ContentObservation.content_version_id.is_not(None),
                )
            )
            if value is not None
        } - visited
    return True


def legacy_content_versions_readable_in_transaction(
    session: Session, *, owner_id: UUID, content_version_ids: tuple[UUID, ...], now: datetime
) -> bool:
    """Unfrozen legacy output must never acquire rights from a modern observation."""
    if not session.in_transaction() or not 1 <= len(content_version_ids) <= 2000:
        return False
    pending = set(content_version_ids)
    visited: set[UUID] = set()
    originals: set[UUID] = set()
    while pending:
        batch = pending - visited
        if not batch:
            break
        if len(visited) + len(batch) > 2000:
            return False
        rows = tuple(
            session.scalars(
                select(ContentObservation).where(
                    ContentObservation.owner_id == owner_id,
                    ContentObservation.content_version_id.in_(batch),
                )
            )
        )
        if {row.content_version_id for row in rows} != batch or any(
            row.input_basis is not None for row in rows
        ):
            return False
        originals.update(row.id for row in rows)
        if len(originals) > 2000:
            return False
        visited.update(batch)
        pending = {
            value
            for value in session.scalars(
                select(ContentObservation.content_version_id).where(
                    ContentObservation.owner_id == owner_id,
                    ContentObservation.id.in_(
                        select(ContentVersionInput.observation_id).where(
                            ContentVersionInput.owner_id == owner_id,
                            ContentVersionInput.content_version_id.in_(batch),
                        )
                    ),
                )
            )
            if value is not None
        } - visited
    return observations_readable_in_transaction(
        session,
        owner_id=owner_id,
        observation_ids=tuple(sorted(originals, key=str)),
        now=now,
    ) and version_inputs_readable_in_transaction(
        session,
        owner_id=owner_id,
        content_version_ids=content_version_ids,
        now=now,
    )
