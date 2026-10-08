"""Resolve actual source provenance without substituting a canonical record's first source."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from content.models import ContentObservation, ContentRecord, ContentVisibilityObservation
from jobs.editorial_member import load_content_job_context_for_editorial_member_in_transaction
from jobs.services import ContentJobContext, load_content_job_context, load_content_job_contexts


@dataclass(frozen=True, slots=True)
class ContentObservationContext:
    observation_id: UUID
    content_id: UUID
    content_version_id: UUID | None
    source_key: str
    native_scope: str | None
    external_id: str
    identity_basis: str | None
    editorial_profile_id: UUID | None
    job: ContentJobContext
    input_basis: str | None = None
    published_at: datetime | None = None


def load_observation_contexts_in_transaction(
    session: Session, *, owner_id: UUID, observation_ids: set[UUID]
) -> dict[UUID, ContentObservationContext]:
    if not session.in_transaction() or len(observation_ids) > 20000:
        raise ValueError("bounded observation contexts require caller transaction")
    rows: list[tuple[ContentObservation, ContentRecord]] = []
    identifiers = tuple(observation_ids)
    for start in range(0, len(identifiers), 1000):
        rows.extend(
            (observation, record)
            for observation, record in session.execute(
                select(ContentObservation, ContentRecord)
                .join(
                    ContentRecord,
                    (ContentRecord.owner_id == ContentObservation.owner_id)
                    & (ContentRecord.id == ContentObservation.content_id),
                )
                .where(
                    ContentObservation.owner_id == owner_id,
                    ContentObservation.id.in_(identifiers[start : start + 1000]),
                )
                .execution_options(populate_existing=True)
            ).all()
        )
    contexts: dict[UUID, ContentJobContext] = {}
    job_ids = tuple({observation.job_id for observation, _ in rows})
    for start in range(0, len(job_ids), 1000):
        contexts.update(
            load_content_job_contexts(
                session, owner_id=owner_id, job_ids=set(job_ids[start : start + 1000])
            )
        )
    members: dict[tuple[UUID, UUID], ContentJobContext | None] = {}
    result = {}
    for observation, record in rows:
        job = contexts.get(observation.job_id)
        fields = _source_fields(observation, record)
        if fields is None or job is None:
            continue
        source, scope, external, basis, profile_id = fields
        if job.source_key != source and profile_id is not None:
            member_key = (observation.job_id, profile_id)
            if member_key not in members:
                members[member_key] = load_content_job_context_for_editorial_member_in_transaction(
                    session, owner_id=owner_id, job_id=observation.job_id, profile_id=profile_id
                )
            job = members[member_key]
        if job is None or job.source_key != source or job.source_capability is None:
            continue
        if profile_id is not None and (
            job.configuration_ref != f"editorial-source:{profile_id}"
            or scope != f"editorial-profile:{profile_id}"
        ):
            continue
        result[observation.id] = ContentObservationContext(
            observation.id,
            observation.content_id,
            observation.content_version_id,
            source,
            scope,
            external,
            basis,
            profile_id,
            job,
            observation.input_basis,
            observation.published_at,
        )
    return result


def _source_fields(
    obs: ContentObservation, record: ContentRecord
) -> tuple[str, str | None, str, str | None, UUID | None] | None:
    if obs.input_basis is None:
        source, scope, external, basis = (
            record.source_key,
            record.native_scope,
            record.external_id,
            record.identity_basis,
        )
        profile_id = None
        if (scope or "").startswith("editorial-profile:"):
            try:
                profile_id = UUID((scope or "").split(":", 1)[1])
            except ValueError:
                return None
    else:
        if obs.source_key is None or obs.source_external_id is None:
            return None
        source, scope, external, basis = (
            obs.source_key,
            obs.source_native_scope,
            obs.source_external_id,
            obs.source_identity_basis,
        )
        profile_id = obs.editorial_profile_id
    return source, scope, external, basis, profile_id


def load_observation_visibilities_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    contexts: dict[UUID, ContentObservationContext],
    decisive_only: bool = False,
) -> dict[UUID, ContentVisibilityObservation]:
    if not session.in_transaction() or len(contexts) > 20000:
        raise ValueError("bounded observation visibility requires caller transaction")
    identifiers = tuple({context.content_id for context in contexts.values()})
    rows: list[ContentVisibilityObservation] = []
    for start in range(0, len(identifiers), 1000):
        rows.extend(
            session.scalars(
                select(ContentVisibilityObservation)
                .where(
                    ContentVisibilityObservation.owner_id == owner_id,
                    ContentVisibilityObservation.content_id.in_(identifiers[start : start + 1000]),
                )
                .order_by(
                    ContentVisibilityObservation.observed_at.desc(),
                    ContentVisibilityObservation.received_at.desc(),
                    ContentVisibilityObservation.id.desc(),
                )
                .execution_options(populate_existing=True)
            )
        )
    if not rows:
        return {}
    jobs = {}
    job_ids = tuple({row.job_id for row in rows})
    for start in range(0, len(job_ids), 1000):
        jobs.update(
            load_content_job_contexts(
                session, owner_id=owner_id, job_ids=set(job_ids[start : start + 1000])
            )
        )
    by_content: dict[UUID, list[ContentVisibilityObservation]] = {}
    for row in rows:
        by_content.setdefault(row.content_id, []).append(row)
    members: dict[tuple[UUID, UUID], ContentJobContext | None] = {}
    result = {}
    for identifier, actual in contexts.items():
        for row in by_content.get(actual.content_id, ()):
            # Failures do not grant or revoke visibility; retain the last source conclusion.
            if decisive_only and row.status in {"transient_failure", "unknown"}:
                continue
            job = jobs.get(row.job_id)
            if (
                job is not None
                and job.source_key != actual.source_key
                and actual.editorial_profile_id
            ):
                member_key = (row.job_id, actual.editorial_profile_id)
                if member_key not in members:
                    members[member_key] = (
                        load_content_job_context_for_editorial_member_in_transaction(
                            session,
                            owner_id=owner_id,
                            job_id=row.job_id,
                            profile_id=actual.editorial_profile_id,
                        )
                    )
                job = members[member_key]
            if (
                job is not None
                and job.source_key == actual.source_key
                and (
                    actual.editorial_profile_id is None
                    or job.configuration_ref == actual.job.configuration_ref
                )
            ):
                result[identifier] = row
                break
    return result


def load_observation_context_in_transaction(
    session: Session, *, owner_id: UUID, observation_id: UUID
) -> ContentObservationContext | None:
    if not session.in_transaction():
        raise RuntimeError("observation context requires caller transaction")
    row = session.execute(
        select(ContentObservation, ContentRecord)
        .join(
            ContentRecord,
            (ContentRecord.owner_id == ContentObservation.owner_id)
            & (ContentRecord.id == ContentObservation.content_id),
        )
        .where(ContentObservation.owner_id == owner_id, ContentObservation.id == observation_id)
        .execution_options(populate_existing=True)
    ).first()
    if row is None:
        return None
    obs, record = row
    if obs.input_basis is None:
        source, scope, external, basis = (
            record.source_key,
            record.native_scope,
            record.external_id,
            record.identity_basis,
        )
        profile_id = None
        if (scope or "").startswith("editorial-profile:"):
            try:
                profile_id = UUID((scope or "").split(":", 1)[1])
            except ValueError:
                return None
    else:
        if obs.source_key is None or obs.source_external_id is None:
            return None
        source, scope, external, basis = (
            obs.source_key,
            obs.source_native_scope,
            obs.source_external_id,
            obs.source_identity_basis,
        )
        profile_id = obs.editorial_profile_id
    job = load_content_job_context(session, owner_id=owner_id, job_id=obs.job_id)
    if job is not None and job.source_key != source and profile_id is not None:
        job = load_content_job_context_for_editorial_member_in_transaction(
            session, owner_id=owner_id, job_id=obs.job_id, profile_id=profile_id
        )
    if job is None or job.source_key != source or job.source_capability is None:
        return None
    if profile_id is not None and (
        job.configuration_ref != f"editorial-source:{profile_id}"
        or scope != f"editorial-profile:{profile_id}"
    ):
        return None
    return ContentObservationContext(
        obs.id,
        obs.content_id,
        obs.content_version_id,
        source,
        scope,
        external,
        basis,
        profile_id,
        job,
        obs.input_basis,
        obs.published_at,
    )


def load_observation_visibility_in_transaction(
    session: Session, *, owner_id: UUID, observation_id: UUID
) -> ContentVisibilityObservation | None:
    """A source-local withdrawal does not declare another independent alias deleted."""
    actual = load_observation_context_in_transaction(
        session, owner_id=owner_id, observation_id=observation_id
    )
    if actual is None:
        return None
    rows = session.scalars(
        select(ContentVisibilityObservation)
        .where(
            ContentVisibilityObservation.owner_id == owner_id,
            ContentVisibilityObservation.content_id == actual.content_id,
        )
        .order_by(
            ContentVisibilityObservation.observed_at.desc(),
            ContentVisibilityObservation.received_at.desc(),
            ContentVisibilityObservation.id.desc(),
        )
        .execution_options(populate_existing=True)
    )
    for row in rows:
        job = load_content_job_context(session, owner_id=owner_id, job_id=row.job_id)
        if (
            job is not None
            and job.source_key != actual.source_key
            and actual.editorial_profile_id is not None
        ):
            job = load_content_job_context_for_editorial_member_in_transaction(
                session,
                owner_id=owner_id,
                job_id=row.job_id,
                profile_id=actual.editorial_profile_id,
            )
        if (
            job is not None
            and job.source_key == actual.source_key
            and (
                actual.editorial_profile_id is None
                or job.configuration_ref == actual.job.configuration_ref
            )
        ):
            return row
    return None
