"""Read cached, lifecycle-admitted avatars without any source network request."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from sqlalchemy.orm import Session

from connections.editorial_icon_services import SourceIconService
from core.errors import ApplicationError, DependencyUnavailableError
from sources.icons_job import SourceIconObjectStorage


@dataclass(frozen=True)
class SourceIconBytes:
    body: bytes
    mime_type: str
    sha256: str


class SourceIconReadingService:
    def __init__(
        self,
        session: Session,
        storage: SourceIconObjectStorage | None,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.session, self.storage, self.clock = session, storage, clock

    def read(
        self, *, owner_id: UUID, profile_id: UUID, mode: Literal["avatar-48", "avatar-96"]
    ) -> SourceIconBytes:
        self.session.rollback()
        with self.session.begin():
            service = SourceIconService(self.session, clock=self.clock)
            reference = service.read_object_in_transaction(
                owner_id=owner_id, profile_id=profile_id, mode=mode
            )
        if reference is None:
            raise ApplicationError("resource_not_found")
        if self.storage is None:
            raise DependencyUnavailableError("media_storage_unavailable")
        body = self.storage.get(reference.object_name, max_bytes=reference.byte_count)
        if (
            len(body) != reference.byte_count
            or hashlib.sha256(body).hexdigest() != reference.sha256
        ):
            raise ApplicationError("resource_not_found")
        with self.session.begin():
            current = SourceIconService(self.session, clock=self.clock).read_object_in_transaction(
                owner_id=owner_id, profile_id=profile_id, mode=mode
            )
            if current != reference:
                raise ApplicationError("resource_not_found")
        return SourceIconBytes(body=body, mime_type=reference.mime_type, sha256=reference.sha256)

    def read_by_source_key(
        self, *, owner_id: UUID, source_key: str, mode: Literal["avatar-48", "avatar-96"]
    ) -> SourceIconBytes:
        self.session.rollback()
        with self.session.begin():
            profile_id = SourceIconService(
                self.session, clock=self.clock
            ).profile_id_by_source_key_in_transaction(owner_id=owner_id, source_key=source_key)
        if profile_id is None:
            raise ApplicationError("resource_not_found")
        return self.read(owner_id=owner_id, profile_id=profile_id, mode=mode)
