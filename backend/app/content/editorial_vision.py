"""Fixed-content first-image admission, independently licensed from article text."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from content.editorial_rendered import read_editorial_rendered_in_transaction
from content.event_reading import load_event_member_content_in_transaction
from content.observation_context import load_observation_context_in_transaction
from content.schemas import EventContentReadReference
from evidence.schemas import AdmittedSourcePayload, DataClass
from evidence.services import (
    RetentionPolicyUnavailableError,
    SourceAccessPolicyService,
    SourceAccessUnavailableError,
)


class EditorialVisionGrant(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    content_id: UUID
    content_version_id: UUID
    rendered_sha256: str
    url: str
    admission: AdmittedSourcePayload


def read_editorial_vision_grant_in_transaction(
    session: Session, *, owner_id: UUID, reference: EventContentReadReference, now: datetime
) -> EditorialVisionGrant | None:
    if not session.in_transaction():
        raise RuntimeError("vision grants require caller transaction")
    rendered = read_editorial_rendered_in_transaction(
        session,
        owner_id=owner_id,
        content_id=reference.content_id,
        content_version_id=reference.content_version_id,
        now=now,
        observation_id=reference.observation_id,
    )
    if rendered is None:
        return None
    first = next((media for media in rendered.media if media.kind == "image"), None)
    readable = load_event_member_content_in_transaction(
        session, owner_id=owner_id, references=(reference,), now=now
    ).get(reference)
    if first is None or readable is None:
        return None
    actual = load_observation_context_in_transaction(
        session,
        owner_id=owner_id,
        observation_id=readable.observation.id,
    )
    context = actual.job if actual else None
    if context is None or context.source_capability is None:
        return None
    try:
        admission = SourceAccessPolicyService(
            session, clock=lambda: now
        ).admit_payload_in_transaction(
            owner_id=owner_id,
            source_key=readable.source_key,
            capability=context.source_capability,
            data_class=DataClass.MEDIA,
            collected_at=readable.observation.observed_at,
            payload={"url": first.url, "vision": "first_image"},
        )
    except (SourceAccessUnavailableError, RetentionPolicyUnavailableError):
        return None
    if admission.fields.get("url") != first.url or admission.fields.get("vision") != "first_image":
        return None
    return EditorialVisionGrant(
        content_id=reference.content_id,
        content_version_id=reference.content_version_id,
        rendered_sha256=rendered.sha256,
        url=first.url,
        admission=admission,
    )
