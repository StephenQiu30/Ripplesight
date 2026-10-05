"""Only lifecycle-readable fixed-version media descriptors and bytes reach public readers."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.errors import ApplicationError, DependencyUnavailableError
from evidence.services import load_readable_resource_ids
from publication.media_mirror_execution import MediaObjectStorage
from publication.media_mirror_models import PublicationMediaFile, PublicationMediaRun
from publication.media_mirror_schemas import MediaRenditionView
from publication.media_mirror_services import (
    RESOURCE_TYPE,
    media_admission_in_transaction,
    require_media_grant_in_transaction,
    require_media_run_source_in_transaction,
)
from publication.publication_models import PublicationRecord
from publication.reading import PublicationReadingService
from publication.schemas import Category, FrozenPublicationReference, PublicMediaView


def load_available_media_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    content_id: UUID,
    content_version_id: UUID,
    policy_revision: int,
    now: datetime,
    redistribute: bool = False,
    observation_id: UUID | None = None,
) -> dict[str, PublicMediaView]:
    if not session.in_transaction():
        raise RuntimeError("media read requires caller transaction")
    run = session.scalar(
        select(PublicationMediaRun).where(
            PublicationMediaRun.owner_id == owner_id,
            PublicationMediaRun.content_id == content_id,
            PublicationMediaRun.content_version_id == content_version_id,
            PublicationMediaRun.policy_revision == policy_revision,
            PublicationMediaRun.observation_id == observation_id,
        )
    )
    if run is None:
        return {}
    try:
        require_media_run_source_in_transaction(session, run, now=now)
        _, candidates, _ = require_media_grant_in_transaction(
            session,
            owner_id=owner_id,
            content_id=content_id,
            version_id=content_version_id,
            policy_revision=policy_revision,
            now=now,
            fixed=FrozenPublicationReference.model_validate(run.fixed_reference),
            expected_body_sha256=run.fixed_reference.get("media_body_sha256"),
        )
    except ApplicationError:
        return {}
    files = list(
        session.scalars(
            select(PublicationMediaFile).where(
                PublicationMediaFile.owner_id == owner_id, PublicationMediaFile.run_id == run.id
            )
        )
    )
    readable = load_readable_resource_ids(
        session,
        owner_id=owner_id,
        resource_type=RESOURCE_TYPE,
        resource_ids={file.id for file in files if file.status == "complete"},
        now=now,
    )
    by_key = {file.media_key: file for file in files}
    result = {}
    for candidate in candidates:
        file = by_key.get(candidate.key)
        if file is None or file.source_url != candidate.original_url:
            continue
        try:
            media_admission_in_transaction(
                session,
                owner_id=owner_id,
                source_key=run.source_key,
                url=file.source_url,
                at=run.created_at,
                now=now,
            )
        except ApplicationError:
            result[candidate.key] = candidate.model_copy(update={"state": "unavailable"})
            continue
        if file.id not in readable:
            state = "unavailable" if file.status == "complete" else file.status
            result[candidate.key] = candidate.model_copy(update={"state": state})
            continue
        mode = "full" if candidate.kind == "image" else "original"
        descriptors = [
            MediaRenditionView(
                mode=key,
                reading_url=f"/api/publication/media/{file.id}/{key}"
                + ("" if redistribute else "/site"),
                mime_type=value["mime_type"],
                width=value["width"],
                height=value["height"],
                frame_count=value["frame_count"],
                byte_count=value["byte_count"],
            )
            for key, value in file.renditions.items()
        ]
        spec = file.renditions[mode]
        result[candidate.key] = candidate.model_copy(
            update={
                "reading_url": f"/api/publication/media/{file.id}/{mode}"
                + ("" if redistribute else "/site"),
                "state": "available",
                "width": spec["width"],
                "height": spec["height"],
                "renditions": descriptors,
            }
        )
    return result


@dataclass(frozen=True)
class MediaBytes:
    body: bytes
    mime_type: str
    sha256: str


class PublicationMediaReadingService:
    def __init__(
        self,
        session: Session,
        storage: MediaObjectStorage | None,
        *,
        public_categories: tuple[Category, ...] = (),
    ) -> None:
        self.session, self.storage = session, storage
        self.public_categories = public_categories

    def _guard(
        self, *, owner_id: UUID, file_id: UUID, mode: str, now: datetime, redistribute: bool
    ) -> dict[str, Any]:
        file = self.session.get(PublicationMediaFile, (owner_id, file_id))
        if file is None or file.status != "complete" or mode not in file.renditions:
            raise ApplicationError("resource_not_found")
        run = self.session.get(PublicationMediaRun, (owner_id, file.run_id))
        assert run
        try:
            require_media_run_source_in_transaction(self.session, run, now=now)
            _, candidates, _ = require_media_grant_in_transaction(
                self.session,
                owner_id=owner_id,
                content_id=run.content_id,
                version_id=run.content_version_id,
                policy_revision=run.policy_revision,
                now=now,
                fixed=FrozenPublicationReference.model_validate(run.fixed_reference),
                expected_body_sha256=run.fixed_reference.get("media_body_sha256"),
            )
        except ApplicationError as error:
            raise ApplicationError("resource_not_found") from error
        try:
            media_admission_in_transaction(
                self.session,
                owner_id=owner_id,
                source_key=run.source_key,
                url=file.source_url,
                at=run.created_at,
                now=now,
            )
        except ApplicationError as error:
            raise ApplicationError("resource_not_found") from error
        if not any(
            item.key == file.media_key
            and item.original_url == file.source_url
            and item.kind == file.kind
            for item in candidates
        ):
            raise ApplicationError("resource_not_found")
        if redistribute or self.public_categories:
            row = self.session.get(PublicationRecord, (owner_id, run.content_id))
            live = (
                PublicationReadingService(self.session, public_categories=self.public_categories)
                ._live(owner_id=owner_id, rows=[row] if row else [], now=now)
                .get(run.content_id)
            )
            if live is None or (redistribute and not live[0].syndicate):
                raise ApplicationError("resource_not_found")
        if file_id not in load_readable_resource_ids(
            self.session,
            owner_id=owner_id,
            resource_type=RESOURCE_TYPE,
            resource_ids={file_id},
            now=now,
        ):
            raise ApplicationError("resource_not_found")
        return dict(file.renditions[mode])

    def read(
        self,
        *,
        owner_id: UUID,
        file_id: UUID,
        mode: str,
        redistribute: bool = True,
        now: datetime | None = None,
    ) -> MediaBytes:
        at = now or datetime.now(UTC)
        self.session.rollback()
        with self.session.begin():
            descriptor = self._guard(
                owner_id=owner_id, file_id=file_id, mode=mode, now=at, redistribute=redistribute
            )
        if self.storage is None:
            raise DependencyUnavailableError("media_storage_unavailable")
        try:
            body = self.storage.get(descriptor["object_name"], max_bytes=descriptor["byte_count"])
        except Exception as error:
            raise DependencyUnavailableError("media_storage_unavailable") from error
        if (
            len(body) != descriptor["byte_count"]
            or hashlib.sha256(body).hexdigest() != descriptor["sha256"]
        ):
            raise DependencyUnavailableError("media_storage_unavailable")
        # Recheck after object I/O using a fresh transaction; revocation cannot reuse old bytes.
        with self.session.begin():
            current = self._guard(
                owner_id=owner_id,
                file_id=file_id,
                mode=mode,
                now=now or datetime.now(UTC),
                redistribute=redistribute,
            )
            if current != descriptor:
                raise ApplicationError("resource_not_found")
        return MediaBytes(body=body, mime_type=descriptor["mime_type"], sha256=descriptor["sha256"])
