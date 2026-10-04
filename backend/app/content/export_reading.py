"""Freeze original permitted content for personal file export without collecting new material."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from content.models import ContentObservation, ContentRecord, ContentVersion, ContentVersionInput
from content.version_inputs import (
    observations_readable_in_transaction,
    version_inputs_readable_in_transaction,
)
from core.errors import ApplicationError
from evidence.services import load_source_access_policy_in_transaction
from jobs.editorial_member import load_content_job_context_for_editorial_member_in_transaction
from jobs.services import load_content_job_context

_EXPORT_PURPOSE = "hotkey:personal-file-export:v1"


@dataclass(frozen=True, slots=True)
class ContentExportItem:
    content_id: UUID
    version_id: UUID
    source_key: str
    canonical_url: str | None
    title: str | None
    body: str | None
    author_name: str | None
    published_at: datetime | None
    discovered_at: datetime
    object_type: str
    text_scope: str
    observation_id: UUID
    input_observation_ids: tuple[UUID, ...]


class FrozenContentExportInput(BaseModel):
    """Server-owned exact observation selection; later observations cannot replace it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version_id: UUID
    observation_id: UUID
    input_observation_ids: tuple[UUID, ...]
    discovered_at: datetime

    @model_validator(mode="after")
    def bounded_originals(self) -> "FrozenContentExportInput":
        if (
            self.discovered_at.utcoffset() is None
            or not 1 <= len(self.input_observation_ids) <= 2000
            or len(set(self.input_observation_ids)) != len(self.input_observation_ids)
            or self.observation_id not in self.input_observation_ids
        ):
            raise ValueError("export selection requires aware exact bounded original inputs")
        return self


def _input_ids(session: Session, *, owner_id: UUID, version_id: UUID) -> set[UUID]:
    observations: set[UUID] = set()
    pending = {version_id}
    visited: set[UUID] = set()
    while pending:
        batch = pending - visited
        if not batch:
            break
        visited.update(batch)
        items = set(
            session.scalars(
                select(ContentVersionInput.observation_id).where(
                    ContentVersionInput.owner_id == owner_id,
                    ContentVersionInput.content_version_id.in_(batch),
                )
            )
        )
        observations.update(items)
        pending = {
            value
            for value in session.scalars(
                select(ContentObservation.content_version_id).where(
                    ContentObservation.owner_id == owner_id,
                    ContentObservation.id.in_(items),
                )
            )
            if value is not None
        } - visited
    return observations


def require_export_observations_in_transaction(
    session: Session, *, owner_id: UUID, observation_ids: tuple[UUID, ...], now: datetime
) -> None:
    """Exact manifest observations retain their original export-purpose permission."""
    if (
        not session.in_transaction()
        or now.utcoffset() is None
        or not 1 <= len(observation_ids) <= 500
        or len(set(observation_ids)) != len(observation_ids)
    ):
        raise ValueError("export observations require aware bounded caller transaction")
    for start in range(0, len(observation_ids), 32):
        if not observations_readable_in_transaction(
            session, owner_id=owner_id, observation_ids=observation_ids[start : start + 32], now=now
        ):
            raise ApplicationError("editorial_material_unavailable")
    input_rows = session.execute(
        select(ContentObservation, ContentVersion, ContentRecord)
        .join(ContentVersion, ContentVersion.id == ContentObservation.content_version_id)
        .join(ContentRecord, ContentRecord.id == ContentObservation.content_id)
        .where(ContentObservation.owner_id == owner_id, ContentObservation.id.in_(observation_ids))
    )
    for original, original_version, original_record in input_rows:
        context = load_content_job_context(session, owner_id=owner_id, job_id=original.job_id)
        if context is not None and context.source_key != original_record.source_key:
            try:
                profile_id = UUID(
                    (original_record.native_scope or "").removeprefix("editorial-profile:")
                )
            except ValueError:
                raise ApplicationError("editorial_material_unavailable") from None
            context = load_content_job_context_for_editorial_member_in_transaction(
                session, owner_id=owner_id, job_id=original.job_id, profile_id=profile_id
            )
        if context is None:
            raise ApplicationError("editorial_material_unavailable")
        policy = load_source_access_policy_in_transaction(
            session,
            owner_id=owner_id,
            source_key=original_record.source_key,
            capability=context.source_capability,
        )
        fields = {"object_type", "text_scope"}
        for field, value in (
            ("title", original_version.title),
            ("body", original_version.body),
            ("author_name", original.author_name),
            ("published_at", original.published_at),
            (
                "canonical_url" if original.canonical_url else "final_url",
                original.canonical_url or original.final_url,
            ),
        ):
            if value is not None:
                fields.add(field)
        if (
            policy is None
            or policy.processing_purpose != _EXPORT_PURPOSE
            or any(policy.field_purposes.get(field) != _EXPORT_PURPOSE for field in fields)
        ):
            raise ApplicationError("editorial_export_not_authorized")


def freeze_export_content_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    content_version_ids: tuple[UUID, ...],
    now: datetime,
    observation_ids: tuple[UUID, ...] | None = None,
) -> tuple[ContentExportItem, ...]:
    if (
        not session.in_transaction()
        or now.utcoffset() is None
        or not 1 <= len(content_version_ids) <= 500
        or len(set(content_version_ids)) != len(content_version_ids)
    ):
        raise ValueError("export freeze requires aware bounded caller transaction")
    if not version_inputs_readable_in_transaction(
        session, owner_id=owner_id, content_version_ids=content_version_ids, now=now
    ):
        raise ApplicationError("editorial_material_unavailable")
    rows = session.execute(
        select(ContentVersion, ContentRecord)
        .join(
            ContentRecord,
            (ContentRecord.owner_id == ContentVersion.owner_id)
            & (ContentRecord.id == ContentVersion.content_id),
        )
        .where(ContentVersion.owner_id == owner_id, ContentVersion.id.in_(content_version_ids))
        .order_by(ContentVersion.id)
    ).all()
    if {version.id for version, _ in rows} != set(content_version_ids):
        raise ApplicationError("editorial_material_unavailable")
    result: list[ContentExportItem] = []
    for version, record in rows:
        observation_query = select(ContentObservation).where(
            ContentObservation.owner_id == owner_id,
            ContentObservation.content_version_id == version.id,
        )
        if observation_ids is not None:
            observation_query = observation_query.where(ContentObservation.id.in_(observation_ids))
        observation = session.scalar(
            observation_query.order_by(
                ContentObservation.received_at.desc(), ContentObservation.id.desc()
            ).limit(1)
        )
        if observation is None:
            raise ApplicationError("editorial_material_unavailable")
        inputs = tuple(
            sorted(
                _input_ids(session, owner_id=owner_id, version_id=version.id) | {observation.id},
                key=str,
            )
        )
        for start in range(0, len(inputs), 32):
            if not observations_readable_in_transaction(
                session, owner_id=owner_id, observation_ids=inputs[start : start + 32], now=now
            ):
                raise ApplicationError("editorial_material_unavailable")
        for start in range(0, len(inputs), 500):
            require_export_observations_in_transaction(
                session, owner_id=owner_id, observation_ids=inputs[start : start + 500], now=now
            )
        discovered = session.scalar(
            select(func.min(ContentObservation.received_at)).where(
                ContentObservation.owner_id == owner_id,
                ContentObservation.content_id == record.id,
            )
        )
        if discovered is None:
            raise ApplicationError("editorial_material_unavailable")
        result.append(
            ContentExportItem(
                content_id=record.id,
                version_id=version.id,
                source_key=record.source_key,
                canonical_url=observation.canonical_url or observation.final_url,
                title=version.title,
                body=version.body,
                author_name=observation.author_name,
                published_at=observation.published_at,
                discovered_at=discovered,
                object_type=record.object_type,
                text_scope=version.text_scope,
                observation_id=observation.id,
                input_observation_ids=inputs,
            )
        )
    return tuple(result)


def restore_export_content_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    frozen_inputs: tuple[FrozenContentExportInput, ...],
    now: datetime,
) -> tuple[ContentExportItem, ...]:
    """Recheck exactly the frozen inputs, never discover a newer equivalent observation."""
    if (
        not session.in_transaction()
        or now.utcoffset() is None
        or not 1 <= len(frozen_inputs) <= 500
        or len({item.version_id for item in frozen_inputs}) != len(frozen_inputs)
    ):
        raise ValueError("export restore requires aware bounded caller transaction")
    result: list[ContentExportItem] = []
    for frozen in frozen_inputs:
        row = session.execute(
            select(ContentVersion, ContentRecord, ContentObservation)
            .join(
                ContentRecord,
                (ContentRecord.owner_id == ContentVersion.owner_id)
                & (ContentRecord.id == ContentVersion.content_id),
            )
            .join(
                ContentObservation,
                (ContentObservation.owner_id == ContentVersion.owner_id)
                & (ContentObservation.content_id == ContentVersion.content_id)
                & (ContentObservation.content_version_id == ContentVersion.id),
            )
            .where(
                ContentVersion.owner_id == owner_id,
                ContentVersion.id == frozen.version_id,
                ContentObservation.id == frozen.observation_id,
            )
        ).one_or_none()
        if row is None:
            raise ApplicationError("editorial_material_unavailable")
        version, record, observation = row
        for start in range(0, len(frozen.input_observation_ids), 500):
            require_export_observations_in_transaction(
                session,
                owner_id=owner_id,
                observation_ids=frozen.input_observation_ids[start : start + 500],
                now=now,
            )
        result.append(
            ContentExportItem(
                content_id=record.id,
                version_id=version.id,
                source_key=record.source_key,
                canonical_url=observation.canonical_url or observation.final_url,
                title=version.title,
                body=version.body,
                author_name=observation.author_name,
                published_at=observation.published_at,
                discovered_at=frozen.discovered_at,
                object_type=record.object_type,
                text_scope=version.text_scope,
                observation_id=observation.id,
                input_observation_ids=frozen.input_observation_ids,
            )
        )
    return tuple(result)
