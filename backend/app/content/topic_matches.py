"""Content-owned immutable local topic matches and exact-input permission checks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from content.models import (
    ContentObservation,
    ContentTopicMatch,
    ContentVersion,
)
from content.version_inputs import (
    observations_readable_in_transaction,
)
from core.errors import ApplicationError
from jobs.editorial_member import load_content_job_context_for_editorial_member_in_transaction
from jobs.services import load_content_job_context
from monitors.services import (
    evaluate_monitor_rules,
    list_active_editorial_topic_rules_in_transaction,
)


@dataclass(frozen=True, slots=True)
class EditorialTopicMatchReference:
    topic_id: UUID
    topic_rule_version: int
    content_id: UUID
    content_version_id: UUID
    observation_id: UUID
    job_id: UUID
    profile_id: UUID
    profile_configuration_version: int
    input_observation_ids: tuple[UUID, ...]
    matched_at: datetime


def editorial_match_inputs_readable_in_transaction(
    session: Session, *, owner_id: UUID, observation_ids: tuple[UUID, ...], now: datetime
) -> bool:
    return observations_readable_in_transaction(
        session, owner_id=owner_id, observation_ids=observation_ids, now=now
    )


def match_editorial_content_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    profile_id: UUID,
    profile_configuration_version: int,
    content_id: UUID,
    content_version_id: UUID,
    observation_id: UUID,
    job_id: UUID,
    connection_id: UUID,
    connection_version: int,
    policy_version: int,
    now: datetime,
    input_observation_ids: tuple[UUID, ...] | None = None,
    grouped_job: bool = False,
) -> tuple[EditorialTopicMatchReference, ...]:
    """One admitted material serves all selected active topics without another fetch/Job."""
    if not session.in_transaction() or now.tzinfo is None:
        raise ValueError("editorial matching requires an aware caller transaction")
    rules = list_active_editorial_topic_rules_in_transaction(
        session,
        owner_id=owner_id,
        profile_id=profile_id,
    )
    if not rules:
        return ()
    session.flush()
    observation = session.get(ContentObservation, observation_id)
    version = session.get(ContentVersion, content_version_id)
    if (
        observation is None
        or version is None
        or observation.owner_id != owner_id
        or version.owner_id != owner_id
        or observation.content_id != content_id
        or version.content_id != content_id
        or observation.content_version_id != content_version_id
        or observation.job_id != job_id
    ):
        raise ApplicationError("editorial_material_unavailable")
    context = (
        load_content_job_context_for_editorial_member_in_transaction(
            session,
            owner_id=owner_id,
            job_id=job_id,
            profile_id=profile_id,
        )
        if grouped_job
        else load_content_job_context(session, owner_id=owner_id, job_id=job_id)
    )
    if (
        context is None
        or context.configuration_ref != f"editorial-source:{profile_id}"
        or context.configuration_version != profile_configuration_version
    ):
        raise ApplicationError("editorial_material_unavailable")
    from content.observation_inputs import freeze_observation_inputs_in_transaction

    inputs = freeze_observation_inputs_in_transaction(
        session,
        owner_id=owner_id,
        observation_ids=tuple(sorted(set(input_observation_ids or (observation_id,)), key=str)),
        now=now,
    )
    if observation_id not in inputs or not editorial_match_inputs_readable_in_transaction(
        session,
        owner_id=owner_id,
        observation_ids=inputs,
        now=now,
    ):
        raise ApplicationError("editorial_material_unavailable")
    text = "\n".join(part for part in (version.title, version.body) if part)
    for rule in rules:
        if not evaluate_monitor_rules(rule.rules, text).matched:
            continue
        session.execute(
            insert(ContentTopicMatch)
            .values(
                id=uuid4(),
                owner_id=owner_id,
                topic_id=rule.topic_id,
                topic_rule_version=rule.topic_rule_version,
                content_id=content_id,
                content_version_id=content_version_id,
                profile_id=profile_id,
                profile_configuration_version=profile_configuration_version,
                observation_id=observation_id,
                job_id=job_id,
                connection_id=connection_id,
                connection_version=connection_version,
                policy_version=policy_version,
                input_observation_ids=[str(item) for item in inputs],
                matched_at=now,
            )
            .on_conflict_do_nothing(constraint="content_topic_matches_frozen_key")
        )
    return readable_editorial_topic_matches_in_transaction(
        session,
        owner_id=owner_id,
        content_ids={content_id},
        now=now,
    )


def readable_editorial_topic_matches_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    now: datetime,
    topic_id: UUID | None = None,
    topic_rule_version: int | None = None,
    content_ids: set[UUID] | None = None,
    content_version_ids: set[UUID] | None = None,
    as_of: datetime | None = None,
) -> tuple[EditorialTopicMatchReference, ...]:
    if not session.in_transaction() or now.tzinfo is None:
        raise ValueError("topic match reads require an aware caller transaction")
    query = select(ContentTopicMatch).where(ContentTopicMatch.owner_id == owner_id)
    if topic_id is not None:
        query = query.where(ContentTopicMatch.topic_id == topic_id)
    if topic_rule_version is not None:
        query = query.where(ContentTopicMatch.topic_rule_version == topic_rule_version)
    if content_ids is not None:
        query = query.where(ContentTopicMatch.content_id.in_(content_ids))
    if content_version_ids is not None:
        query = query.where(ContentTopicMatch.content_version_id.in_(content_version_ids))
    if as_of is not None:
        query = query.where(ContentTopicMatch.matched_at < as_of)
    result: list[EditorialTopicMatchReference] = []
    for row in session.scalars(query.order_by(ContentTopicMatch.matched_at, ContentTopicMatch.id)):
        inputs = tuple(UUID(value) for value in row.input_observation_ids)
        if not editorial_match_inputs_readable_in_transaction(
            session,
            owner_id=owner_id,
            observation_ids=inputs,
            now=now,
        ):
            continue
        result.append(
            EditorialTopicMatchReference(
                topic_id=row.topic_id,
                topic_rule_version=row.topic_rule_version,
                content_id=row.content_id,
                content_version_id=row.content_version_id,
                observation_id=row.observation_id,
                job_id=row.job_id,
                profile_id=row.profile_id,
                profile_configuration_version=row.profile_configuration_version,
                input_observation_ids=inputs,
                matched_at=row.matched_at,
            )
        )
    return tuple(result)
