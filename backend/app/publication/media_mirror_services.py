"""Explicit mirror acceptance freezes publication inputs and uses the existing Job/Outbox."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from content.event_reading import load_event_member_content_in_transaction
from content.observation_context import load_observation_context_in_transaction
from content.schemas import EventContentReadReference
from content.version_inputs import legacy_content_versions_readable_in_transaction
from core.errors import ApplicationError
from evidence.schemas import AdmittedSourcePayload, DataClass
from evidence.services import (
    RetentionPolicyUnavailableError,
    SourceAccessPolicyService,
    SourceAccessUnavailableError,
    load_source_access_readiness,
)
from jobs.schemas import JobAcceptanceInput, JobObservationContext
from jobs.services import JobService
from publication.media import body_presentation
from publication.media_mirror_models import PublicationMediaFile, PublicationMediaRun
from publication.media_mirror_schemas import MediaMirrorInput, MediaMirrorRunView, MediaState
from publication.reading import full_text_grant_in_transaction
from publication.schemas import FrozenPublicationReference, PublicMediaView
from sources.contracts import SourceCapability

CONFIGURATION_REF = "publication:media-mirror-v1"
RESOURCE_TYPE = "publication_media"
MAX_CANDIDATES = 32


def media_admission_in_transaction(
    session: Session, *, owner_id: UUID, source_key: str, url: str, at: datetime, now: datetime
) -> AdmittedSourcePayload:
    if not load_source_access_readiness(session, owner_id=owner_id, now=now).get(
        (source_key, SourceCapability.PAGE_CONTENT), False
    ):
        raise ApplicationError("publication_revision_conflict")
    try:
        admitted = SourceAccessPolicyService(
            session, clock=lambda: now
        ).admit_payload_in_transaction(
            owner_id=owner_id,
            source_key=source_key,
            capability=SourceCapability.PAGE_CONTENT,
            data_class=DataClass.MEDIA,
            collected_at=at,
            payload={"url": url},
        )
        if admitted.fields.get("url") != url:
            raise ApplicationError("publication_revision_conflict")
        return admitted
    except (SourceAccessUnavailableError, RetentionPolicyUnavailableError, ValueError) as error:
        raise ApplicationError("publication_revision_conflict") from error


def source_material_in_transaction(
    session: Session, *, owner_id: UUID, reference: FrozenPublicationReference, now: datetime
) -> tuple[str, UUID]:
    ref = EventContentReadReference(
        content_id=reference.content_id,
        content_version_id=reference.content_version_id,
        observation_id=reference.observation_id,
        input_observation_ids=reference.input_observation_ids,
        legacy_strict=reference.observation_id is None,
    )
    snapshot = load_event_member_content_in_transaction(
        session, owner_id=owner_id, references=(ref,), now=now
    ).get(ref)
    if snapshot is None:
        raise ApplicationError("publication_revision_conflict")
    return snapshot.source_key, snapshot.observation.id


def require_media_run_source_in_transaction(
    session: Session, run: PublicationMediaRun, *, now: datetime
) -> None:
    """A nullable legacy source marker must never bypass a modern observation's source FK."""
    fixed = FrozenPublicationReference.model_validate(run.fixed_reference)
    if (
        fixed.observation_id != run.observation_id
        or fixed.content_id != run.content_id
        or fixed.content_version_id != run.content_version_id
    ):
        raise ApplicationError("publication_revision_conflict")
    if run.observation_id is None:
        if (
            run.observation_source_key is not None
            or not legacy_content_versions_readable_in_transaction(
                session,
                owner_id=run.owner_id,
                content_version_ids=(run.content_version_id,),
                now=now,
            )
        ):
            raise ApplicationError("publication_revision_conflict")
        source, _ = source_material_in_transaction(
            session, owner_id=run.owner_id, reference=fixed, now=now
        )
        if source != run.source_key:
            raise ApplicationError("publication_revision_conflict")
        return
    actual = load_observation_context_in_transaction(
        session, owner_id=run.owner_id, observation_id=run.observation_id
    )
    if (
        actual is None
        or actual.content_id != run.content_id
        or actual.content_version_id != run.content_version_id
        or actual.source_key != run.source_key
        or run.observation_source_key
        != (actual.source_key if actual.input_basis is not None else None)
    ):
        raise ApplicationError("publication_revision_conflict")


def require_media_grant_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    content_id: UUID,
    version_id: UUID,
    policy_revision: int,
    now: datetime,
    fixed: FrozenPublicationReference | None = None,
    expected_body_sha256: str | None = None,
) -> tuple[FrozenPublicationReference, list[PublicMediaView], str]:
    grant = full_text_grant_in_transaction(
        session,
        owner_id=owner_id,
        content_id=content_id,
        content_version_id=version_id,
        policy_revision=policy_revision,
        now=now,
    )
    if (
        not grant.granted
        or grant.reference is None
        or grant.body is None
        or (
            fixed is not None
            and (
                grant.reference.content_id != fixed.content_id
                or grant.reference.content_version_id != fixed.content_version_id
                or grant.reference.policy_revision != fixed.policy_revision
                or grant.reference.observation_id != fixed.observation_id
                or grant.reference.input_observation_ids != fixed.input_observation_ids
            )
        )
        or not grant.body_sha256
        or (expected_body_sha256 is not None and grant.body_sha256 != expected_body_sha256)
    ):
        raise ApplicationError("publication_revision_conflict")
    return (
        grant.reference,
        [
            item
            for item in body_presentation(
                grant.body, body_format=grant.body_format, media=grant.media
            )[2]
            if item.kind in {"image", "video"}
        ],
        grant.body_sha256,
    )


def run_view(
    session: Session, run: PublicationMediaRun, *, replayed: bool = False
) -> MediaMirrorRunView:
    files = list(
        session.scalars(
            select(PublicationMediaFile).where(
                PublicationMediaFile.owner_id == run.owner_id, PublicationMediaFile.run_id == run.id
            )
        )
    )
    return MediaMirrorRunView(
        id=run.id,
        job_id=run.job_id,
        content_id=run.content_id,
        content_version_id=run.content_version_id,
        policy_revision=run.policy_revision,
        status=cast(MediaState, run.status),
        candidate_count=len(files),
        available_count=sum(item.status == "complete" for item in files),
        unavailable_count=sum(
            item.status in {"unknown", "failed", "stale", "cancelled"} for item in files
        ),
        reason=run.reason,
        replayed=replayed,
    )


class PublicationMediaService:
    def __init__(self, session: Session, *, enabled: bool = False) -> None:
        self.session, self.enabled = session, enabled

    def request(
        self,
        *,
        owner_id: UUID,
        content_id: UUID,
        command: MediaMirrorInput,
        now: datetime | None = None,
    ) -> MediaMirrorRunView:
        at = now or datetime.now(UTC)
        if not self.enabled:
            raise ApplicationError("invalid_publication_input")
        self.session.rollback()
        with self.session.begin():
            return self.request_in_transaction(
                owner_id=owner_id, content_id=content_id, command=command, now=at
            )

    def request_in_transaction(
        self, *, owner_id: UUID, content_id: UUID, command: MediaMirrorInput, now: datetime
    ) -> MediaMirrorRunView:
        if not self.session.in_transaction() or now.utcoffset() is None:
            raise RuntimeError("media acceptance requires an aware caller transaction")
        if not self.enabled:
            raise ApplicationError("invalid_publication_input")
        at = now
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "content": str(content_id),
                    "version": str(command.content_version_id),
                    "policy": command.policy_revision,
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
            {"key": f"media-admit:{owner_id}:{content_id}"},
        )
        op = self.session.scalar(
            select(PublicationMediaRun).where(
                PublicationMediaRun.owner_id == owner_id,
                PublicationMediaRun.operation_id == command.operation_id,
            )
        )
        if op:
            if op.input_fingerprint != fingerprint:
                raise ApplicationError("publication_revision_conflict")
            require_media_run_source_in_transaction(self.session, op, now=at)
            return run_view(self.session, op, replayed=True)
        reference, candidates, body_sha256 = require_media_grant_in_transaction(
            self.session,
            owner_id=owner_id,
            content_id=content_id,
            version_id=command.content_version_id,
            policy_revision=command.policy_revision,
            now=at,
        )
        if len(candidates) > MAX_CANDIDATES:
            raise ApplicationError("invalid_publication_input")
        existing = self.session.scalar(
            select(PublicationMediaRun).where(
                PublicationMediaRun.owner_id == owner_id,
                PublicationMediaRun.content_id == content_id,
                PublicationMediaRun.content_version_id == command.content_version_id,
                PublicationMediaRun.policy_revision == command.policy_revision,
                PublicationMediaRun.observation_id == reference.observation_id,
            )
        )
        if existing:
            require_media_run_source_in_transaction(self.session, existing, now=at)
            return run_view(self.session, existing, replayed=True)
        source_key, actual_id = source_material_in_transaction(
            self.session, owner_id=owner_id, reference=reference, now=at
        )
        actual = load_observation_context_in_transaction(
            self.session, owner_id=owner_id, observation_id=actual_id
        )
        if actual is None or actual.source_key != source_key:
            raise ApplicationError("publication_revision_conflict")
        for candidate in candidates:
            media_admission_in_transaction(
                self.session,
                owner_id=owner_id,
                source_key=source_key,
                url=candidate.original_url,
                at=at,
                now=at,
            )
        run_id = uuid4()
        job = JobService(self.session, clock=lambda: at).accept_in_transaction(
            owner_id=owner_id,
            command=JobAcceptanceInput(
                operation_id=command.operation_id,
                kind="publication.media_mirror",
                observation=JobObservationContext(
                    configuration_ref=CONFIGURATION_REF, configuration_version=1
                ),
                scope={
                    "media_run_id": str(run_id),
                    "content_id": str(content_id),
                    "content_version_id": str(command.content_version_id),
                    "policy_revision": command.policy_revision,
                },
            ),
        )
        run = PublicationMediaRun(
            owner_id=owner_id,
            id=run_id,
            operation_id=command.operation_id,
            job_id=job.id,
            content_id=content_id,
            content_version_id=command.content_version_id,
            observation_id=reference.observation_id,
            observation_source_key=actual.source_key if actual.input_basis is not None else None,
            policy_revision=command.policy_revision,
            source_key=source_key,
            fixed_reference={
                **reference.model_dump(mode="json"),
                "media_body_sha256": body_sha256,
            },
            input_fingerprint=fingerprint,
            status="queued",
            reason=None,
            created_at=at,
            updated_at=at,
        )
        self.session.add(run)
        self.session.flush()
        for candidate in candidates:
            self.session.add(
                PublicationMediaFile(
                    owner_id=owner_id,
                    id=uuid4(),
                    run_id=run_id,
                    media_key=candidate.key,
                    source_url=candidate.original_url,
                    kind=candidate.kind,
                    status="pending",
                    mime_type=None,
                    content_sha256=None,
                    byte_count=None,
                    renditions={},
                    evidence_resource_id=None,
                    reason=None,
                    created_at=at,
                    updated_at=at,
                )
            )
        self.session.flush()
        return run_view(self.session, run)

    def get(
        self, *, owner_id: UUID, run_id: UUID, now: datetime | None = None
    ) -> MediaMirrorRunView | None:
        self.session.rollback()
        with self.session.begin():
            run = self.session.get(PublicationMediaRun, (owner_id, run_id))
            if run is None:
                return None
            require_media_run_source_in_transaction(self.session, run, now=now or datetime.now(UTC))
            require_media_grant_in_transaction(
                self.session,
                owner_id=owner_id,
                content_id=run.content_id,
                version_id=run.content_version_id,
                policy_revision=run.policy_revision,
                now=now or datetime.now(UTC),
                fixed=FrozenPublicationReference.model_validate(run.fixed_reference),
                expected_body_sha256=run.fixed_reference.get("media_body_sha256"),
            )
            return run_view(self.session, run)
