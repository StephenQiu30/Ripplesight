"""Pin the actual event observations; shared versions never substitute their source inputs."""

from dataclasses import replace
from datetime import datetime
from typing import cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from content.event_reading import load_event_member_content_in_transaction
from content.observation_context import load_observation_contexts_in_transaction
from content.observation_inputs import freeze_observation_inputs_in_transaction
from content.schemas import EventContentReadReference
from content.version_inputs import observations_readable_in_transaction
from core.errors import ApplicationError
from events.fact_models import EventFactMember
from events.models import EventMember
from events.schemas import EventInput


class _InputReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    content_id: UUID
    content_version_id: UUID
    source_key: str
    observation_id: UUID
    observation_source_key: str | None = None
    annotation_id: UUID | None = None
    input_observation_ids: tuple[UUID, ...] = Field(default=(), max_length=2000)
    representative_comment_id: UUID | None = None
    representative_comment_observation_id: UUID | None = None
    first_seen_at: datetime
    first_seen_basis: str
    matched_keywords: tuple[str, ...] = Field(max_length=200)
    native_target_content_ids: tuple[UUID, ...] = Field(max_length=200)
    editorial_frame: dict[str, object] | None = None
    provenance_fingerprint: str | None = None


class _Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    basis: str = "observations_v1"
    items: tuple[_InputReference, ...] = Field(min_length=1, max_length=20)
    input_observation_ids: tuple[UUID, ...] = Field(min_length=1, max_length=2000)


def event_content_reference(
    item: EventInput | EventMember, *, include_comment: bool = True
) -> EventContentReadReference:
    inputs = event_input_observation_ids(item)
    if isinstance(item, EventMember) and item.observation_id is not None:
        # Source matching is independently verified by the Content helper at every read.
        marker = item.input_manifest.get("observation_source_key") if item.input_manifest else None
        if marker != item.observation_source_key:
            inputs = (UUID(int=0),)
    return EventContentReadReference(
        content_id=item.content_id,
        content_version_id=item.content_version_id,
        representative_comment_id=item.representative_comment_id if include_comment else None,
        observation_id=item.observation_id,
        representative_comment_observation_id=(
            item.representative_comment_observation_id if include_comment else None
        ),
        input_observation_ids=inputs,
        legacy_strict=isinstance(item, EventMember) and item.observation_id is None,
        expected_source_key=item.source_key if isinstance(item, EventMember) else None,
        observation_source_key=item.observation_source_key,
    )


def event_input_observation_ids(item: EventInput | EventMember) -> tuple[UUID, ...]:
    if isinstance(item, EventInput):
        return item.input_observation_ids
    if item.input_manifest is None:
        return ()
    try:
        if item.input_manifest["basis"] != "observations_v1":
            raise ValueError("unsupported event input basis")
        values = tuple(UUID(str(value)) for value in item.input_manifest["input_observation_ids"])
        if not 1 <= len(values) <= 2000 or item.observation_id not in values:
            raise ValueError("invalid fixed event inputs")
        return values
    except (KeyError, ValueError, TypeError):
        # Invalid persisted manifests cannot fall back to the canonical/latest material.
        return (UUID(int=0),)


def event_member_input_manifest(item: EventInput) -> dict[str, object] | None:
    if item.observation_id is None:
        return None
    return {
        "basis": "observations_v1",
        "observation_source_key": item.observation_source_key,
        "input_observation_ids": [str(value) for value in item.input_observation_ids],
    }


def load_fact_observation_inputs_in_transaction(
    session: Session, *, owner_id: UUID, fact_ids: tuple[UUID, ...], now: datetime
) -> dict[UUID, tuple[UUID, ...]]:
    """A fact's frame needs every member, including members outside a recall page."""
    if not session.in_transaction() or len(fact_ids) > 2000:
        raise RuntimeError("fact input reads require a bounded caller transaction")
    if not fact_ids:
        return {}
    rows = session.execute(
        select(EventFactMember, EventMember)
        .outerjoin(
            EventMember,
            and_(
                EventMember.owner_id == EventFactMember.owner_id,
                EventMember.id == EventFactMember.event_member_id,
            ),
        )
        .where(
            EventFactMember.owner_id == owner_id,
            EventFactMember.fact_id.in_(fact_ids),
            EventFactMember.removed_revision.is_(None),
        )
        .limit(2001)
    ).all()
    if len(rows) > 2000:
        return {}
    by_fact: dict[UUID, list[EventMember]] = {}
    unavailable: set[UUID] = set()
    for fact_member, member in rows:
        if (
            member is None
            or member.removed_revision is not None
            or member.content_id != fact_member.content_id
            or member.content_version_id != fact_member.content_version_id
        ):
            unavailable.add(fact_member.fact_id)
        else:
            by_fact.setdefault(fact_member.fact_id, []).append(member)
    result = {}
    for fact_id, members in by_fact.items():
        if fact_id in unavailable:
            continue
        references = tuple(event_content_reference(member) for member in members)
        readings = load_event_member_content_in_transaction(
            session, owner_id=owner_id, references=references, now=now
        )
        if any(
            ref not in readings or readings[ref].representative_comment_state == "unavailable"
            for ref in references
        ):
            continue
        selected: list[UUID] = []
        for ref in references:
            reading = readings[ref]
            selected.extend((reading.observation.id, *ref.input_observation_ids))
            comment = reading.representative_comment
            if comment is not None:
                selected.append(comment.observation.id)
        roots = tuple(dict.fromkeys(selected))
        try:
            result[fact_id] = freeze_observation_inputs_in_transaction(
                session, owner_id=owner_id, observation_ids=roots, now=now
            )
        except ApplicationError:
            continue
    return result


def freeze_event_inputs_in_transaction(
    session: Session, *, owner_id: UUID, inputs: tuple[EventInput, ...], now: datetime
) -> tuple[tuple[EventInput, ...], dict[str, object]]:
    """Discovery may choose an observation once; persistence pins that exact choice."""
    if not session.in_transaction() or not 1 <= len(inputs) <= 20:
        raise ValueError("event inputs require a bounded caller transaction")
    references = tuple(event_content_reference(item) for item in inputs)
    readings = load_event_member_content_in_transaction(
        session, owner_id=owner_id, references=references, now=now
    )
    actual_contexts = load_observation_contexts_in_transaction(
        session,
        owner_id=owner_id,
        observation_ids={reading.observation.id for reading in readings.values()},
    )
    selected = []
    frozen = []
    for item, reference in zip(inputs, references, strict=True):
        reading = readings.get(reference)
        if (
            item.owner_id != owner_id
            or reading is None
            or reading.source_key != item.source_key
            or reading.representative_comment_state == "unavailable"
            or reading.observation.content_version is None
        ):
            raise ApplicationError("editorial_material_unavailable")
        comment = reading.representative_comment
        actual = actual_contexts.get(reading.observation.id)
        if actual is None or actual.source_key != item.source_key:
            raise ApplicationError("editorial_material_unavailable")
        comment_id = comment.observation.id if comment else None
        if item.representative_comment_id is not None and comment_id is None:
            raise ApplicationError("editorial_material_unavailable")
        selected.append(reading.observation.id)
        selected.extend(item.input_observation_ids)
        if comment_id is not None:
            selected.append(comment_id)
        frozen.append(
            replace(
                item,
                observation_id=reading.observation.id,
                observation_source_key=actual.source_key
                if actual.input_basis is not None
                else None,
                representative_comment_observation_id=comment_id,
            )
        )
    closure = freeze_observation_inputs_in_transaction(
        session, owner_id=owner_id, observation_ids=tuple(dict.fromkeys(selected)), now=now
    )
    frozen = [replace(item, input_observation_ids=closure) for item in frozen]
    return tuple(frozen), _Manifest(
        items=tuple(
            _InputReference(
                content_id=item.content_id,
                content_version_id=item.content_version_id,
                source_key=item.source_key,
                observation_id=cast(UUID, item.observation_id),
                observation_source_key=item.observation_source_key,
                annotation_id=item.annotation_id,
                input_observation_ids=item.input_observation_ids,
                representative_comment_id=item.representative_comment_id,
                representative_comment_observation_id=item.representative_comment_observation_id,
                first_seen_at=item.first_seen_at,
                first_seen_basis=item.first_seen_basis,
                matched_keywords=tuple(sorted(item.matched_keywords)),
                native_target_content_ids=tuple(sorted(item.native_target_content_ids, key=str)),
                editorial_frame=item.editorial_frame,
                provenance_fingerprint=item.provenance_fingerprint,
            )
            for item in frozen
        ),
        input_observation_ids=closure,
    ).model_dump(mode="json")


def load_frozen_event_inputs_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    topic_id: UUID,
    manifest: dict[str, object],
    now: datetime,
) -> tuple[EventInput, ...]:
    if not session.in_transaction():
        raise RuntimeError("event input read requires caller transaction")
    try:
        fixed = _Manifest.model_validate(manifest)
        if fixed.basis != "observations_v1" or not observations_readable_in_transaction(
            session, owner_id=owner_id, observation_ids=fixed.input_observation_ids, now=now
        ):
            return ()
        references = tuple(
            EventContentReadReference(
                content_id=item.content_id,
                content_version_id=item.content_version_id,
                representative_comment_id=item.representative_comment_id,
                observation_id=item.observation_id,
                representative_comment_observation_id=item.representative_comment_observation_id,
                input_observation_ids=item.input_observation_ids,
                expected_source_key=item.source_key,
                observation_source_key=item.observation_source_key,
            )
            for item in fixed.items
        )
        readings = load_event_member_content_in_transaction(
            session, owner_id=owner_id, references=references, now=now
        )
        selected = tuple(
            dict.fromkeys(
                identity
                for item in fixed.items
                for identity in (
                    item.observation_id,
                    item.representative_comment_observation_id,
                    *item.input_observation_ids,
                )
                if identity is not None
            )
        )
        if (
            freeze_observation_inputs_in_transaction(
                session, owner_id=owner_id, observation_ids=selected, now=now
            )
            != fixed.input_observation_ids
        ):
            return ()
    except (ValueError, ValidationError, ApplicationError):
        return ()
    actual_contexts = load_observation_contexts_in_transaction(
        session,
        owner_id=owner_id,
        observation_ids={item.observation_id for item in fixed.items},
    )
    inputs = []
    for item, reference in zip(fixed.items, references, strict=True):
        reading = readings.get(reference)
        version = reading.observation.content_version if reading else None
        actual = actual_contexts.get(item.observation_id)
        if (
            reading is None
            or version is None
            or actual is None
            or item.observation_source_key
            != (actual.source_key if actual.input_basis is not None else None)
            or reading.source_key != item.source_key
            or reading.observation.id != item.observation_id
            or reading.representative_comment_state == "unavailable"
            or item.first_seen_at.utcoffset() is None
        ):
            return ()
        inputs.append(
            EventInput(
                owner_id=owner_id,
                topic_id=topic_id,
                content_id=item.content_id,
                content_version_id=item.content_version_id,
                source_key=item.source_key,
                title=version.title or "",
                body=version.body,
                first_seen_at=item.first_seen_at,
                first_seen_basis=item.first_seen_basis,
                matched_keywords=frozenset(item.matched_keywords),
                representative_comment_id=item.representative_comment_id,
                native_target_content_ids=frozenset(item.native_target_content_ids),
                editorial_frame=item.editorial_frame,
                provenance_fingerprint=item.provenance_fingerprint,
                observation_id=item.observation_id,
                observation_source_key=item.observation_source_key,
                representative_comment_observation_id=item.representative_comment_observation_id,
                input_observation_ids=fixed.input_observation_ids,
                annotation_id=item.annotation_id,
            )
        )
        if item.provenance_fingerprint is not None:
            from analysis.event_reading import load_frozen_editorial_event_input_in_transaction

            editorial = load_frozen_editorial_event_input_in_transaction(
                session,
                owner_id=owner_id,
                content_id=item.content_id,
                content_version_id=item.content_version_id,
                observation_id=item.observation_id,
                provenance_fingerprint=item.provenance_fingerprint,
                now=now,
            )
            if editorial is None:
                return ()
            inputs[-1] = replace(
                inputs[-1], title=editorial.title, body=editorial.summary or editorial.raw_body
            )
    return tuple(inputs)
