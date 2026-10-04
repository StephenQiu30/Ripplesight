"""Invalidate narratives containing removed members without reinterpreting the remaining set."""

import json
from contextlib import suppress
from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from content.observation_inputs import observation_input_closure_in_transaction
from core.errors import ApplicationError
from events.embedding_models import EventContentEmbedding
from events.fact_models import (
    EventDerivedContent,
    EventFact,
    EventFactMember,
    EventRevisionOperation,
)
from events.heat_models import EventAttentionSignal, EventAttentionSnapshot
from events.models import Event, EventCandidate, EventMember
from events.story_models import EventStoryLink
from jobs.services import load_job_execution_configuration


def _uses(value: object, identifiers: set[str]) -> bool:
    if isinstance(value, str):
        return value in identifiers
    if isinstance(value, dict):
        return any(_uses(item, identifiers) for item in (*value.keys(), *value.values()))
    if isinstance(value, (list, tuple)):
        return any(_uses(item, identifiers) for item in value)
    return False


def purge_event_content_inputs_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    content_version_ids: tuple[UUID, ...],
    content_ids: tuple[UUID, ...],
    now: datetime,
    observation_ids: tuple[UUID, ...] = (),
    legacy_content_version_ids: tuple[UUID, ...] = (),
) -> None:
    if not session.in_transaction():
        raise RuntimeError("event cleanup requires caller transaction")
    removed_observations = set(observation_ids)
    member_rows = list(
        session.scalars(
            select(EventMember).where(
                EventMember.owner_id == owner_id,
                or_(
                    EventMember.content_version_id.in_(content_version_ids),
                    EventMember.representative_comment_id.in_(content_ids),
                    EventMember.observation_id.in_(observation_ids),
                    EventMember.representative_comment_observation_id.in_(observation_ids),
                    (
                        EventMember.observation_id.is_(None)
                        & EventMember.content_version_id.in_(legacy_content_version_ids)
                    ),
                ),
            )
        )
    )
    if removed_observations:
        selected_ids = {row.id for row in member_rows}
        for member in session.scalars(select(EventMember).where(EventMember.owner_id == owner_id)):
            if member.id in selected_ids or member.observation_id is None:
                continue
            roots = tuple(
                value
                for value in (member.observation_id, member.representative_comment_observation_id)
                if value is not None
            )
            if _uses(member.input_manifest, {str(value) for value in observation_ids}):
                member_rows.append(member)
                continue
            try:
                closure = observation_input_closure_in_transaction(
                    session, owner_id=owner_id, observation_ids=roots
                )
            except ApplicationError:
                # A missing input fails closed; it cannot be repaired by another source.
                closure = roots
            if removed_observations.intersection(closure):
                member_rows.append(member)
    event_ids = {row.event_id for row in member_rows}
    affected_observations = tuple(
        removed_observations
        | {
            value
            for row in member_rows
            for value in (row.observation_id, row.representative_comment_observation_id)
            if value is not None
        }
    )
    event_ids.update(
        session.scalars(
            select(EventAttentionSignal.event_id).where(
                EventAttentionSignal.owner_id == owner_id,
                or_(
                    EventAttentionSignal.content_version_id.in_(content_version_ids),
                    EventAttentionSignal.observation_id.in_(affected_observations),
                ),
            )
        )
    )
    fact_ids = set(
        session.scalars(
            select(EventFactMember.fact_id).where(
                EventFactMember.owner_id == owner_id,
                or_(
                    EventFactMember.content_version_id.in_(content_version_ids),
                    EventFactMember.event_member_id.in_({row.id for row in member_rows}),
                ),
            )
        )
    )
    for event in session.scalars(
        select(Event).where(Event.owner_id == owner_id, Event.id.in_(event_ids)).with_for_update()
    ):
        event.title = "材料已撤回"
        event.summary = "固定输入已删除。原叙述不可再使用。"
        event.revision += 1
        event.updated_at = now
    for fact in session.scalars(
        select(EventFact).where(EventFact.owner_id == owner_id, EventFact.id.in_(fact_ids))
    ):
        fact.title = "材料已撤回"
        fact.summary = "固定输入已删除。原事实叙述不可再使用。"
        fact.frame = None
        fact.revision += 1
        fact.updated_at = now
    session.execute(
        delete(EventDerivedContent).where(
            EventDerivedContent.owner_id == owner_id, EventDerivedContent.event_id.in_(event_ids)
        )
    )
    session.execute(
        delete(EventAttentionSnapshot).where(
            EventAttentionSnapshot.owner_id == owner_id,
            EventAttentionSnapshot.event_id.in_(event_ids),
        )
    )
    session.execute(
        delete(EventStoryLink).where(
            EventStoryLink.owner_id == owner_id,
            or_(
                EventStoryLink.first_event_id.in_(event_ids),
                EventStoryLink.second_event_id.in_(event_ids),
            ),
        )
    )
    session.execute(
        delete(EventAttentionSignal).where(
            EventAttentionSignal.owner_id == owner_id,
            or_(
                EventAttentionSignal.content_version_id.in_(content_version_ids),
                EventAttentionSignal.observation_id.in_(affected_observations),
            ),
        )
    )
    identifiers = {
        str(item)
        for item in (*content_version_ids, *content_ids, *observation_ids, *event_ids, *fact_ids)
    }
    for candidate in session.scalars(
        select(EventCandidate).where(EventCandidate.owner_id == owner_id)
    ):
        if identifiers.intersection(candidate.member_version_ids) or _uses(
            candidate.input_manifest, {str(value) for value in observation_ids}
        ):
            session.delete(candidate)
    for operation in session.scalars(
        select(EventRevisionOperation).where(EventRevisionOperation.owner_id == owner_id)
    ):
        if any(
            _uses(value, identifiers)
            for value in (operation.before_state, operation.after_state, operation.result)
        ):
            session.delete(operation)
    for embedding in session.scalars(
        select(EventContentEmbedding).where(EventContentEmbedding.owner_id == owner_id)
    ):
        configuration = (
            load_job_execution_configuration(session, job_id=embedding.job_id)
            if embedding.job_id is not None
            else None
        )
        manifest = None
        if configuration is not None:
            with suppress(ValueError, TypeError):
                manifest = json.loads(str(configuration.scope.get("input_observation_ids")))
        if embedding.content_version_id in content_version_ids or _uses(
            manifest,
            {str(value) for value in observation_ids},
        ):
            session.delete(embedding)
    session.execute(
        delete(EventFactMember).where(
            EventFactMember.owner_id == owner_id,
            EventFactMember.content_version_id.in_(content_version_ids),
        )
    )
    session.execute(
        delete(EventMember).where(
            EventMember.owner_id == owner_id, EventMember.id.in_({row.id for row in member_rows})
        )
    )
