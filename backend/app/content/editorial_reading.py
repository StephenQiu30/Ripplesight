from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from content.event_reading import load_event_member_content_in_transaction
from content.models import ContentObservation, ContentRecord, ContentVersion
from content.schemas import EditorialDiscoveryView, EventContentReadReference, EventContentReadView
from core.errors import ApplicationError
from evidence.schemas import DataClass
from evidence.services import (
    RetentionPolicyUnavailableError,
    SourceAccessPolicyService,
    SourceAccessUnavailableError,
    readable_resource_ids_query,
)
from jobs.schemas import CollectionScanKind
from jobs.services import load_content_job_context


def scan_editorial_content_ids_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    limit: int,
    after: UUID | None = None,
    source_key: str | None = None,
) -> tuple[UUID, ...]:
    """Scan stored post identities; publication performs the live permission check."""
    if not session.in_transaction() or not 1 <= limit <= 1001:
        raise ValueError("content identity scan requires a bounded caller transaction")
    query = select(ContentRecord.id).where(
        ContentRecord.owner_id == owner_id, ContentRecord.object_type.in_(("post", "webpage"))
    )
    if source_key is not None:
        query = query.where(ContentRecord.source_key == source_key)
    if after is not None:
        query = query.where(ContentRecord.id > after)
    return tuple(session.scalars(query.order_by(ContentRecord.id).limit(limit)))


def load_latest_editorial_content_in_transaction(
    session: Session, *, owner_id: UUID, content_ids: tuple[UUID, ...], now: datetime
) -> dict[UUID, EventContentReadView]:
    """Read original fixed versions without creating an analysis run or a request."""
    if not session.in_transaction() or len(content_ids) > 1000:
        raise ValueError("raw content reads require a bounded caller transaction")
    if not content_ids:
        return {}
    rows = session.execute(
        select(ContentObservation.content_id, ContentObservation.content_version_id)
        .where(
            ContentObservation.owner_id == owner_id,
            ContentObservation.content_id.in_(content_ids),
            ContentObservation.content_version_id.is_not(None),
            ContentObservation.id.in_(
                readable_resource_ids_query(
                    owner_id=owner_id, resource_type="content_observation", now=now
                )
            ),
        )
        .distinct(ContentObservation.content_id)
        .order_by(
            ContentObservation.content_id,
            ContentObservation.observed_at.desc(),
            ContentObservation.received_at.desc(),
            ContentObservation.id.desc(),
        )
    ).all()
    result = {}
    for row in rows:
        reference = EventContentReadReference(content_id=row[0], content_version_id=row[1])
        item = frozen_editorial_content_in_transaction(
            session, owner_id=owner_id, reference=reference, now=now
        )
        if item is None:
            continue
        try:
            require_editorial_content_permission_in_transaction(
                session, owner_id=owner_id, reference=reference, now=now, lock_policies=False
            )
        except ApplicationError as error:
            if error.code != "editorial_material_unavailable":
                raise
            continue
        result[row[0]] = item
    return result


def latest_editorial_references_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    source_key: str,
    now: datetime,
    limit: int = 100,
    after: UUID | None = None,
) -> tuple[EventContentReadReference, ...]:
    """Return latest readable observations, never an older body's version to fill a newer gap."""
    if not session.in_transaction() or not 1 <= limit <= 1000:
        raise ValueError("editorial scan needs a transaction and bounded limit")
    readable = readable_resource_ids_query(
        owner_id=owner_id, resource_type="content_observation", now=now
    )
    latest = (
        select(ContentObservation.content_id, ContentObservation.content_version_id)
        .join(
            ContentRecord,
            (ContentRecord.owner_id == ContentObservation.owner_id)
            & (ContentRecord.id == ContentObservation.content_id),
        )
        .where(
            ContentObservation.owner_id == owner_id,
            ContentRecord.source_key == source_key,
            ContentRecord.object_type.in_(("post", "webpage")),
            ContentObservation.id.in_(readable),
        )
        .distinct(ContentObservation.content_id)
        .order_by(
            ContentObservation.content_id,
            ContentObservation.observed_at.desc(),
            ContentObservation.received_at.desc(),
            ContentObservation.id.desc(),
        )
        .subquery()
    )
    statement = select(latest.c.content_id, latest.c.content_version_id).where(
        latest.c.content_version_id.is_not(None)
    )
    if after is not None:
        statement = statement.where(latest.c.content_id > after)
    rows = session.execute(statement.order_by(latest.c.content_id).limit(limit))
    return tuple(
        EventContentReadReference(content_id=row[0], content_version_id=row[1]) for row in rows
    )


def latest_quoted_reference_in_transaction(
    session: Session, *, owner_id: UUID, main: EventContentReadView, now: datetime
) -> EventContentReadReference | None:
    if not session.in_transaction():
        raise RuntimeError("quote reads require the caller's transaction")
    version = main.observation.content_version
    if version is None:
        return None
    targets = [
        relation.target_content_id
        for relation in version.relations
        if relation.relation_type.value == "quote" and relation.target_content_id
    ]
    if not targets:
        return None
    readable = readable_resource_ids_query(
        owner_id=owner_id, resource_type="content_observation", now=now
    )
    row = session.execute(
        select(ContentObservation.content_id, ContentObservation.content_version_id)
        .where(
            ContentObservation.owner_id == owner_id,
            ContentObservation.content_id == targets[0],
            ContentObservation.content_version_id.is_not(None),
            ContentObservation.id.in_(readable),
        )
        .order_by(
            ContentObservation.observed_at.desc(),
            ContentObservation.received_at.desc(),
            ContentObservation.id.desc(),
        )
        .limit(1)
    ).first()
    return (
        None
        if row is None
        else EventContentReadReference(content_id=row[0], content_version_id=row[1])
    )


def editorial_first_received_at_in_transaction(
    session: Session, *, owner_id: UUID, reference: EventContentReadReference
) -> datetime | None:
    """Use the frozen version's first local receipt, rather than an engagement refresh."""
    if not session.in_transaction():
        raise RuntimeError("editorial receipt reads require the caller's transaction")
    return session.scalar(
        select(ContentVersion.created_at).where(
            ContentVersion.owner_id == owner_id,
            ContentVersion.content_id == reference.content_id,
            ContentVersion.id == reference.content_version_id,
        )
    )


def frozen_editorial_content_in_transaction(
    session: Session, *, owner_id: UUID, reference: EventContentReadReference, now: datetime
) -> EventContentReadView | None:
    item = load_event_member_content_in_transaction(
        session, owner_id=owner_id, references=(reference,), now=now
    ).get(reference)
    if (
        item is None
        or item.object_type == "comment"
        or (
            item.current_visibility is not None
            and item.current_visibility.status.value in {"deleted", "restricted"}
        )
    ):
        return None
    return item


def require_editorial_content_permission_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    reference: EventContentReadReference,
    now: datetime,
    lock_policies: bool = True,
) -> None:
    """Check only the exact original fields that the editorial AI input consumes."""
    if not session.in_transaction():
        raise RuntimeError("editorial permission checks require caller transaction")
    item = frozen_editorial_content_in_transaction(
        session, owner_id=owner_id, reference=reference, now=now
    )
    if item is None or item.observation.content_version is None:
        raise ApplicationError("editorial_material_unavailable")
    observation = session.get(ContentObservation, item.observation.id)
    context = (
        load_content_job_context(session, owner_id=owner_id, job_id=observation.job_id)
        if observation is not None
        else None
    )
    if context is None or context.source_key != item.source_key:
        raise ApplicationError("editorial_material_unavailable")
    version = item.observation.content_version
    payload: dict[str, object] = {"external_id": item.external_id}
    for field, value in (
        ("title", version.title),
        ("body", version.body),
        ("author_external_id", item.observation.author_external_id),
        ("canonical_url", item.observation.canonical_url),
        ("final_url", item.observation.final_url if not item.observation.canonical_url else None),
        (
            "published_at",
            item.observation.published_at.isoformat() if item.observation.published_at else None,
        ),
    ):
        if value is not None and value != "":
            payload[field] = value
    policy = SourceAccessPolicyService(session, clock=lambda: now)
    try:
        if lock_policies:
            policy.require_admission_ready_in_transaction(
                owner_id=owner_id,
                source_key=item.source_key,
                capability=context.source_capability,
                data_class=DataClass.STRUCTURED,
            )
        admitted = policy.admit_payload_in_transaction(
            owner_id=owner_id,
            source_key=item.source_key,
            capability=context.source_capability,
            data_class=DataClass.STRUCTURED,
            collected_at=item.observation.observed_at,
            payload=payload,
        )
    except (SourceAccessUnavailableError, RetentionPolicyUnavailableError) as error:
        raise ApplicationError("editorial_material_unavailable") from error
    if admitted.expires_at <= now or any(
        admitted.fields.get(key) != value for key, value in payload.items()
    ):
        raise ApplicationError("editorial_material_unavailable")


def require_analysis_content_permissions_in_transaction(
    session: Session, *, owner_id: UUID, content_version_ids: tuple[UUID, ...], now: datetime
) -> None:
    """Check frozen post/comment text without adding an editorial-only visibility contract."""
    if not session.in_transaction() or not 1 <= len(content_version_ids) <= 2000:
        raise ValueError("analysis permission checks require bounded caller transaction")
    rows = session.execute(
        select(ContentVersion.id, ContentVersion.content_id).where(
            ContentVersion.owner_id == owner_id,
            ContentVersion.id.in_(content_version_ids),
        )
    ).all()
    if {row[0] for row in rows} != set(content_version_ids):
        raise ApplicationError("editorial_material_unavailable")
    references = tuple(
        EventContentReadReference(content_id=row[1], content_version_id=row[0]) for row in rows
    )
    items = load_event_member_content_in_transaction(
        session, owner_id=owner_id, references=references, now=now
    )
    if len(items) != len(references):
        raise ApplicationError("editorial_material_unavailable")
    policy = SourceAccessPolicyService(session, clock=lambda: now)
    for item in items.values():
        version = item.observation.content_version
        observation = session.get(ContentObservation, item.observation.id)
        context = (
            load_content_job_context(session, owner_id=owner_id, job_id=observation.job_id)
            if observation
            else None
        )
        if (
            version is None
            or context is None
            or context.source_key != item.source_key
            or (
                item.current_visibility is not None
                and item.current_visibility.status in {"deleted", "restricted"}
            )
        ):
            raise ApplicationError("editorial_material_unavailable")
        payload: dict[str, object] = {}
        if version.title:
            payload["title"] = version.title
        if version.body:
            payload["body"] = version.body
        if not payload:
            raise ApplicationError("editorial_material_unavailable")
        try:
            policy.require_admission_ready_in_transaction(
                owner_id=owner_id,
                source_key=item.source_key,
                capability=context.source_capability,
                data_class=DataClass.STRUCTURED,
            )
            admitted = policy.admit_payload_in_transaction(
                owner_id=owner_id,
                source_key=item.source_key,
                capability=context.source_capability,
                data_class=DataClass.STRUCTURED,
                collected_at=item.observation.observed_at,
                payload=payload,
            )
        except (SourceAccessUnavailableError, RetentionPolicyUnavailableError) as error:
            raise ApplicationError("editorial_material_unavailable") from error
        if admitted.expires_at <= now or any(
            admitted.fields.get(key) != value for key, value in payload.items()
        ):
            raise ApplicationError("editorial_material_unavailable")


def editorial_discovery_in_transaction(
    session: Session, *, owner_id: UUID, content_id: UUID
) -> EditorialDiscoveryView | None:
    if not session.in_transaction():
        raise RuntimeError("discovery metadata requires the caller's transaction")
    first = session.scalar(
        select(ContentObservation)
        .where(ContentObservation.owner_id == owner_id, ContentObservation.content_id == content_id)
        .order_by(ContentObservation.received_at, ContentObservation.id)
        .limit(1)
    )
    if first is None:
        return None
    context = load_content_job_context(session, owner_id=owner_id, job_id=first.job_id)
    kind = context.scan_kind if context is not None else None
    return EditorialDiscoveryView(
        timeline_at=first.published_at or first.received_at,
        first_received_at=first.received_at,
        backfill=None if kind is None else kind is CollectionScanKind.BACKFILL,
    )
