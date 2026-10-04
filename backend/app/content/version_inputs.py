"""Frozen actual-input dependency graph for content versions, using original policy facts."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from content.models import (
    ContentObservation,
    ContentRecord,
    ContentVersion,
    ContentVersionInput,
    ContentVisibilityObservation,
)
from core.errors import ApplicationError
from evidence.schemas import DataClass
from evidence.services import (
    RetentionPolicyUnavailableError,
    SourceAccessPolicyService,
    SourceAccessUnavailableError,
    load_readable_resources_in_transaction,
    readable_resource_ids_query,
)
from jobs.editorial_member import load_content_job_context_for_editorial_member_in_transaction
from jobs.services import load_content_job_context


def observations_readable_in_transaction(
    session: Session, *, owner_id: UUID, observation_ids: tuple[UUID, ...], now: datetime
) -> bool:
    """ALL actual original observations, fields and current policies; pause is not revocation."""
    if not session.in_transaction() or now.tzinfo is None:
        raise ValueError("match inputs require an aware caller transaction")
    if not 1 <= len(observation_ids) <= 32 or len(set(observation_ids)) != len(observation_ids):
        return False
    rows = session.execute(
        select(ContentObservation, ContentRecord, ContentVersion)
        .join(
            ContentRecord,
            (ContentRecord.owner_id == ContentObservation.owner_id)
            & (ContentRecord.id == ContentObservation.content_id),
        )
        .join(
            ContentVersion,
            (ContentVersion.owner_id == ContentObservation.owner_id)
            & (ContentVersion.id == ContentObservation.content_version_id),
        )
        .where(
            ContentObservation.owner_id == owner_id,
            ContentObservation.id.in_(observation_ids),
            ContentObservation.id.in_(
                readable_resource_ids_query(
                    owner_id=owner_id,
                    resource_type="content_observation",
                    now=now,
                )
            ),
        )
    ).all()
    if {observation.id for observation, _, _ in rows} != set(observation_ids):
        return False
    original_permissions = load_readable_resources_in_transaction(
        session,
        owner_id=owner_id,
        resource_type="content_observation",
        resource_ids=set(observation_ids),
        now=now,
    )
    policies = SourceAccessPolicyService(session, clock=lambda: now)
    for observation, record, version in rows:
        visibility = session.scalar(
            select(ContentVisibilityObservation)
            .where(
                ContentVisibilityObservation.owner_id == owner_id,
                ContentVisibilityObservation.content_id == record.id,
            )
            .order_by(
                ContentVisibilityObservation.observed_at.desc(),
                ContentVisibilityObservation.received_at.desc(),
                ContentVisibilityObservation.id.desc(),
            )
            .limit(1)
        )
        if visibility is not None and visibility.status != "visible":
            return False
        context = load_content_job_context(session, owner_id=owner_id, job_id=observation.job_id)
        if context is None or context.source_capability is None:
            return False
        if context.source_key != record.source_key:
            prefix = "editorial-profile:"
            if not (record.native_scope or "").startswith(prefix):
                return False
            try:
                profile_id = UUID((record.native_scope or "")[len(prefix) :])
            except ValueError:
                return False
            context = load_content_job_context_for_editorial_member_in_transaction(
                session,
                owner_id=owner_id,
                job_id=observation.job_id,
                profile_id=profile_id,
            )
            if context is None or context.source_key != record.source_key:
                return False
        source_key = context.source_key
        payload: dict[str, object] = {}
        for field in ("title", "body"):
            value = getattr(version, field)
            if value:
                payload[field] = value
        try:
            admitted = policies.admit_payload_in_transaction(
                owner_id=owner_id,
                source_key=source_key,
                capability=context.source_capability,
                data_class=DataClass.STRUCTURED,
                collected_at=observation.observed_at,
                payload=payload,
            )
        except (SourceAccessUnavailableError, RetentionPolicyUnavailableError, ValueError):
            return False
        original = original_permissions.get(observation.id)
        if (
            original is None
            or admitted.policy_id != original.source_policy_id
            or admitted.policy_version != original.source_policy_version
            or admitted.retention_policy_id != original.retention_policy_id
            or admitted.retention_policy_version != original.retention_policy_version
            or admitted.expires_at <= now
            or any(admitted.fields.get(k) != v for k, v in payload.items())
        ):
            return False
    return True


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
