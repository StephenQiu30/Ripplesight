"""Strong native mapping preserves original source identity and permissions."""

import hashlib
import json
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from content.models import ContentNativeIdentity, ContentRecord
from core.errors import ApplicationError
from sources.editorial_identity import EditorialNativeIdentityProof


def resolve_native_content_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    source_key: str,
    native_scope: str | None,
    external_id: str,
    object_type: str,
    proof: EditorialNativeIdentityProof,
    now: datetime,
) -> ContentRecord | None:
    # Both first-native and ordinary-profile keys lock in stable order to avoid concurrent
    # first inserts producing separate records. Locks carry no access grant.
    keys = (
        (
            "native",
            str(owner_id),
            proof.platform,
            proof.object_type,
            proof.namespace,
            proof.native_id,
        ),
        ("source", str(owner_id), source_key, object_type, native_scope, external_id),
    )
    locks = sorted(
        {
            int.from_bytes(hashlib.sha256(json.dumps(k).encode()).digest()[:8], "big", signed=True)
            for k in keys
        }
    )
    for lock in locks:
        session.execute(text("SELECT pg_advisory_xact_lock(:lock)"), {"lock": lock})
    local = session.scalar(
        select(ContentRecord)
        .where(
            ContentRecord.owner_id == owner_id,
            ContentRecord.source_key == source_key,
            ContentRecord.object_type == object_type,
            ContentRecord.native_scope.is_not_distinct_from(native_scope),
            ContentRecord.external_id == external_id,
        )
        .with_for_update()
    )
    mapping = session.scalar(
        select(ContentNativeIdentity)
        .where(
            ContentNativeIdentity.owner_id == owner_id,
            ContentNativeIdentity.platform == proof.platform,
            ContentNativeIdentity.object_type == proof.object_type,
            ContentNativeIdentity.namespace == proof.namespace,
            ContentNativeIdentity.native_id == proof.native_id,
        )
        .with_for_update()
    )
    if mapping is None:
        return local
    if local is not None and local.id != mapping.content_id:
        raise ApplicationError("idempotency_conflict")
    return session.scalar(
        select(ContentRecord)
        .where(ContentRecord.owner_id == owner_id, ContentRecord.id == mapping.content_id)
        .with_for_update()
    )


def bind_native_content_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    content_id: UUID,
    proof: EditorialNativeIdentityProof,
    now: datetime,
) -> None:
    existing = session.scalar(
        select(ContentNativeIdentity).where(
            ContentNativeIdentity.owner_id == owner_id,
            ContentNativeIdentity.platform == proof.platform,
            ContentNativeIdentity.object_type == proof.object_type,
            ContentNativeIdentity.namespace == proof.namespace,
            ContentNativeIdentity.native_id == proof.native_id,
        )
    )
    if existing is not None:
        if existing.content_id != content_id:
            raise ApplicationError("idempotency_conflict")
        return
    session.add(
        ContentNativeIdentity(
            id=uuid4(),
            owner_id=owner_id,
            content_id=content_id,
            platform=proof.platform,
            object_type=proof.object_type,
            namespace=proof.namespace,
            native_id=proof.native_id,
            created_at=now,
        )
    )
    session.flush()
