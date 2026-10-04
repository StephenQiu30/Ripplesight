from __future__ import annotations

from datetime import datetime
from typing import Literal, cast
from uuid import UUID

from sqlalchemy import Select, and_, func, select, tuple_
from sqlalchemy.orm import Session

from content.models import (
    ContentObservation,
    ContentRecord,
    ContentThread,
    ContentVersion,
    ContentVersionRelation,
    ContentVisibilityObservation,
)
from content.schemas import (
    ContentMetricView,
    ContentObservationView,
    ContentRelationType,
    ContentTextOrigin,
    ContentTextScope,
    ContentTruncationReason,
    ContentVersionRelationView,
    ContentVersionView,
    ContentVisibilityView,
    EventCommentReadView,
    EventContentOriginalTime,
    EventContentReadReference,
    EventContentReadView,
    EventSignalContentInput,
    EventSignalContentPage,
)
from content.version_inputs import version_inputs_readable_in_transaction
from evidence.services import readable_resource_ids_query
from jobs.source_scopes import load_collection_source_scopes_in_transaction


def load_event_member_content_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    references: tuple[EventContentReadReference, ...],
    now: datetime,
) -> dict[EventContentReadReference, EventContentReadView]:
    """Project exact member versions; never substitute a newer readable version."""
    if not session.in_transaction():
        raise RuntimeError("event content reads require the caller's transaction")
    if not references:
        return {}
    if len(references) > 500:
        batched: dict[EventContentReadReference, EventContentReadView] = {}
        for offset in range(0, len(references), 500):
            batched.update(
                load_event_member_content_in_transaction(
                    session,
                    owner_id=owner_id,
                    references=references[offset : offset + 500],
                    now=now,
                )
            )
        return batched
    readable = readable_resource_ids_query(
        owner_id=owner_id, resource_type="content_observation", now=now
    )
    requested = {(ref.content_id, ref.content_version_id) for ref in references}
    versions_and_records = session.execute(
        select(ContentRecord, ContentVersion)
        .join(
            ContentVersion,
            and_(
                ContentVersion.owner_id == ContentRecord.owner_id,
                ContentVersion.content_id == ContentRecord.id,
            ),
        )
        .where(
            ContentRecord.owner_id == owner_id,
            ContentVersion.id.in_({version_id for _, version_id in requested}),
        )
    ).all()
    fixed = {
        (record.id, version.id): (record, version)
        for record, version in versions_and_records
        if (record.id, version.id) in requested
        and version_inputs_readable_in_transaction(
            session, owner_id=owner_id, content_version_ids=(version.id,), now=now
        )
    }
    if not fixed:
        return {}
    observations = session.scalars(
        select(ContentObservation)
        .where(
            ContentObservation.owner_id == owner_id,
            ContentObservation.content_version_id.in_({version_id for _, version_id in fixed}),
            ContentObservation.id.in_(readable),
        )
        .order_by(
            ContentObservation.observed_at.desc(),
            ContentObservation.received_at.desc(),
            ContentObservation.id.desc(),
        )
    )
    selected: dict[tuple[UUID, UUID], tuple[ContentRecord, ContentVersion, ContentObservation]] = {}
    for observation in observations:
        if observation.content_version_id is None:
            continue
        pair = (observation.content_id, observation.content_version_id)
        material = fixed.get(pair)
        if material is None:
            continue
        record, version = material
        selected.setdefault(pair, (record, version, observation))
    if not selected:
        return {}
    job_ids = tuple(sorted({row[2].job_id for row in selected.values()}, key=str))
    collection_scopes = {}
    for offset in range(0, len(job_ids), 1000):
        collection_scopes.update(
            load_collection_source_scopes_in_transaction(
                session, owner_id=owner_id, job_ids=job_ids[offset : offset + 1000]
            )
        )

    comment_pairs = {
        (ref.content_id, ref.representative_comment_id)
        for ref in references
        if ref.representative_comment_id is not None
        and (ref.content_id, ref.content_version_id) in selected
    }
    comments: dict[tuple[UUID, UUID], tuple[ContentThread, ContentVersion, ContentObservation]] = {}
    if comment_pairs:
        comment_rows = session.execute(
            select(ContentThread, ContentVersion, ContentObservation)
            .join(
                ContentRecord,
                and_(
                    ContentRecord.owner_id == ContentThread.owner_id,
                    ContentRecord.id == ContentThread.content_id,
                    ContentRecord.object_type == "comment",
                ),
            )
            .join(
                ContentObservation,
                and_(
                    ContentObservation.owner_id == ContentThread.owner_id,
                    ContentObservation.content_id == ContentThread.content_id,
                ),
            )
            .join(
                ContentVersion,
                and_(
                    ContentVersion.owner_id == ContentObservation.owner_id,
                    ContentVersion.content_id == ContentObservation.content_id,
                    ContentVersion.id == ContentObservation.content_version_id,
                ),
            )
            .where(
                ContentThread.owner_id == owner_id,
                tuple_(ContentThread.post_content_id, ContentThread.content_id).in_(comment_pairs),
                ContentObservation.id.in_(readable),
            )
            .order_by(
                ContentObservation.observed_at.desc(),
                ContentObservation.received_at.desc(),
                ContentObservation.id.desc(),
            )
        ).all()
        for thread, version, observation in comment_rows:
            if not version_inputs_readable_in_transaction(
                session, owner_id=owner_id, content_version_ids=(version.id,), now=now
            ):
                continue
            comments.setdefault(
                (thread.post_content_id, thread.content_id), (thread, version, observation)
            )

    versions = {version.id: version for _, version, _ in selected.values()}
    versions.update({version.id: version for _, version, _ in comments.values()})
    version_views = _version_views(session, owner_id=owner_id, versions=versions, readable=readable)
    visibility: dict[UUID, ContentVisibilityView] = {}
    for row in session.scalars(
        select(ContentVisibilityObservation)
        .where(
            ContentVisibilityObservation.owner_id == owner_id,
            ContentVisibilityObservation.content_id.in_({key[0] for key in selected}),
        )
        .order_by(
            ContentVisibilityObservation.observed_at.desc(),
            ContentVisibilityObservation.received_at.desc(),
            ContentVisibilityObservation.id.desc(),
        )
    ):
        visibility.setdefault(row.content_id, ContentVisibilityView.model_validate(row))
    result: dict[EventContentReadReference, EventContentReadView] = {}
    for reference in references:
        selection = selected.get((reference.content_id, reference.content_version_id))
        if selection is None:
            continue
        record, version, observation = selection
        comment_id = reference.representative_comment_id
        comment = comments.get((record.id, comment_id)) if comment_id else None
        comment_view = None
        if comment is not None:
            thread, comment_version, comment_observation = comment
            comment_view = EventCommentReadView(
                id=thread.content_id,
                root_content_id=thread.root_content_id,
                parent_content_id=thread.parent_content_id,
                parent_relation_status=cast(
                    Literal["root", "observed", "unavailable", "unresolved"],
                    thread.parent_relation_status,
                ),
                observation=_observation_view(
                    comment_observation, version_views[comment_version.id]
                ),
            )
        result[reference] = EventContentReadView(
            id=record.id,
            source_key=record.source_key,
            object_type=cast(Literal["post", "comment", "webpage"], record.object_type),
            native_scope=record.native_scope,
            collection_scope=(
                collection_scopes[observation.job_id].selector_ref
                if observation.job_id in collection_scopes
                and collection_scopes[observation.job_id].source_key == record.source_key
                else None
            ),
            external_id=record.external_id,
            identity_basis=cast(Literal["guid", "url_fallback"] | None, record.identity_basis),
            observation=_observation_view(observation, version_views[version.id]),
            current_visibility=visibility.get(record.id),
            representative_comment=comment_view,
            representative_comment_state=(
                "readable" if comment_view else "unavailable" if comment_id else "none"
            ),
        )
    return result


def _version_views(
    session: Session,
    *,
    owner_id: UUID,
    versions: dict[UUID, ContentVersion],
    readable: Select[tuple[UUID]],
) -> dict[UUID, ContentVersionView]:
    relations = list(
        session.scalars(
            select(ContentVersionRelation)
            .where(
                ContentVersionRelation.owner_id == owner_id,
                ContentVersionRelation.content_version_id.in_(versions),
            )
            .order_by(ContentVersionRelation.relation_type, ContentVersionRelation.id)
        )
    )
    sources = {
        content_id: source_key
        for content_id, source_key in session.execute(
            select(ContentRecord.id, ContentRecord.source_key).where(
                ContentRecord.owner_id == owner_id,
                ContentRecord.id.in_({version.content_id for version in versions.values()}),
            )
        ).all()
    }

    targets: dict[tuple[str, str | None, str], UUID] = {}
    if relations:
        for target in session.scalars(
            select(ContentRecord).where(
                ContentRecord.owner_id == owner_id,
                ContentRecord.object_type == "post",
                ContentRecord.source_key.in_(set(sources.values())),
                ContentRecord.external_id.in_({row.target_external_id for row in relations}),
                select(ContentObservation.id)
                .where(
                    ContentObservation.owner_id == owner_id,
                    ContentObservation.content_id == ContentRecord.id,
                    ContentObservation.id.in_(readable),
                )
                .exists(),
            )
        ):
            targets[(target.source_key, target.native_scope, target.external_id)] = target.id
    grouped: dict[UUID, list[ContentVersionRelationView]] = {}
    for relation in relations:
        source = sources[versions[relation.content_version_id].content_id]
        grouped.setdefault(relation.content_version_id, []).append(
            ContentVersionRelationView(
                relation_type=ContentRelationType(relation.relation_type),
                target_native_scope=relation.target_native_scope,
                target_external_id=relation.target_external_id,
                target_author_external_id=relation.target_author_external_id,
                target_content_id=targets.get(
                    (source, relation.target_native_scope, relation.target_external_id)
                ),
            )
        )
    return {
        version.id: ContentVersionView(
            id=version.id,
            text_scope=ContentTextScope(version.text_scope),
            text_origin=ContentTextOrigin(version.text_origin),
            text_origin_ref=version.text_origin_ref,
            title=version.title,
            body=version.body,
            truncation_reason=ContentTruncationReason(version.truncation_reason)
            if version.truncation_reason
            else None,
            relations=grouped.get(version.id, []),
        )
        for version in versions.values()
    }


def load_native_event_targets_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    references: tuple[EventContentReadReference, ...],
    now: datetime,
) -> dict[UUID, frozenset[UUID]]:
    """Resolve fixed quote/repost/reply identities using current readable source evidence."""
    readings = load_event_member_content_in_transaction(
        session, owner_id=owner_id, references=references, now=now
    )
    result = {}
    readable = readable_resource_ids_query(
        owner_id=owner_id, resource_type="content_observation", now=now
    )
    threads = {
        row.content_id: row
        for row in session.scalars(
            select(ContentThread).where(
                ContentThread.owner_id == owner_id,
                ContentThread.content_id.in_([ref.content_id for ref in references]),
            )
        )
    }
    possible = {
        identity
        for thread in threads.values()
        for identity in (thread.post_content_id, thread.root_content_id, thread.parent_content_id)
        if identity is not None
    }
    allowed = (
        set(
            session.scalars(
                select(ContentObservation.content_id).where(
                    ContentObservation.owner_id == owner_id,
                    ContentObservation.content_id.in_(possible),
                    ContentObservation.id.in_(readable),
                )
            )
        )
        if possible
        else set()
    )
    for reference, reading in readings.items():
        version = reading.observation.content_version
        if version is None or reading.representative_comment_state == "unavailable":
            continue
        targets = {
            row.target_content_id for row in version.relations if row.target_content_id is not None
        }
        thread = threads.get(reference.content_id)
        if thread is not None:
            targets.update(
                identity
                for identity in (
                    thread.post_content_id,
                    thread.root_content_id,
                    thread.parent_content_id,
                )
                if identity in allowed
            )
        result[reference.content_version_id] = frozenset(targets)
    return result


def _observation_view(
    observation: ContentObservation,
    version: ContentVersionView,
) -> ContentObservationView:
    return ContentObservationView(
        id=observation.id,
        observed_at=observation.observed_at,
        received_at=observation.received_at,
        published_at=observation.published_at,
        published_at_fractional_digits=observation.published_at_fractional_digits,
        canonical_url=observation.canonical_url,
        final_url=observation.final_url,
        author_external_id=observation.author_external_id,
        metrics=ContentMetricView.model_validate(observation),
        content_version=version,
    )


def load_event_content_original_times_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    references: tuple[EventContentReadReference, ...],
) -> dict[UUID, EventContentOriginalTime]:
    """Original identity time for exact versions; repeated collection cannot reset it."""
    if not session.in_transaction():
        raise RuntimeError("original content times require a caller transaction")
    identities = {(reference.content_id, reference.content_version_id) for reference in references}
    if not identities:
        return {}
    result = {}
    for version, record, published, observed in session.execute(
        select(
            ContentVersion,
            ContentRecord,
            func.min(ContentObservation.published_at),
            func.min(ContentObservation.observed_at),
        )
        .join(
            ContentRecord,
            and_(
                ContentRecord.owner_id == ContentVersion.owner_id,
                ContentRecord.id == ContentVersion.content_id,
            ),
        )
        .outerjoin(
            ContentObservation,
            and_(
                ContentObservation.owner_id == ContentRecord.owner_id,
                ContentObservation.content_id == ContentRecord.id,
            ),
        )
        .where(
            ContentVersion.owner_id == owner_id,
            tuple_(ContentVersion.content_id, ContentVersion.id).in_(identities),
        )
        .group_by(ContentVersion.id, ContentRecord.id)
    ):
        result[version.id] = EventContentOriginalTime(
            content_id=record.id,
            content_version_id=version.id,
            source_time=published or observed or record.created_at,
            basis="published" if published is not None else "discovered",
        )
    return result


def list_recent_signal_content_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    source_keys: tuple[str, ...],
    since: datetime,
    now: datetime,
    after_content_id: UUID | None = None,
    limit: int = 1000,
) -> EventSignalContentPage:
    """Recent discovery, not a metric-refresh receipt; never fall back from the latest version."""
    from content.editorial_reading import editorial_discovery_in_transaction
    from content.report_reading import report_inputs_readable_in_transaction

    if (
        not session.in_transaction()
        or since.utcoffset() is None
        or now.utcoffset() is None
        or since > now
        or not 1 <= limit <= 1000
        or len(source_keys) > 1000
    ):
        raise ValueError("signal scan requires bounded aware caller transaction")
    first = (
        select(
            ContentObservation.content_id,
            func.min(ContentObservation.received_at).label("received"),
        )
        .where(ContentObservation.owner_id == owner_id)
        .group_by(ContentObservation.content_id)
        .subquery()
    )
    latest = (
        select(ContentObservation.content_id, ContentObservation.content_version_id)
        .where(ContentObservation.owner_id == owner_id)
        .distinct(ContentObservation.content_id)
        .order_by(
            ContentObservation.content_id,
            ContentObservation.observed_at.desc(),
            ContentObservation.received_at.desc(),
            ContentObservation.id.desc(),
        )
        .subquery()
    )
    query = (
        select(ContentRecord.id, latest.c.content_version_id)
        .join(first, first.c.content_id == ContentRecord.id)
        .join(latest, latest.c.content_id == ContentRecord.id)
        .where(
            ContentRecord.owner_id == owner_id,
            ContentRecord.source_key.in_(source_keys),
            first.c.received >= since,
            first.c.received <= now,
            latest.c.content_version_id.is_not(None),
        )
        .order_by(ContentRecord.id)
        .limit(limit + 1)
    )
    if after_content_id is not None:
        query = query.where(ContentRecord.id > after_content_id)
    rows = session.execute(query).all()
    references = tuple(
        EventContentReadReference(content_id=row[0], content_version_id=row[1])
        for row in rows[:limit]
    )
    readings = load_event_member_content_in_transaction(
        session, owner_id=owner_id, references=references, now=now
    )
    times = load_event_content_original_times_in_transaction(
        session, owner_id=owner_id, references=references
    )
    result = []
    for reference in references:
        reading = readings.get(reference)
        original = times.get(reference.content_version_id)
        discovery = editorial_discovery_in_transaction(
            session, owner_id=owner_id, content_id=reference.content_id
        )
        if (
            reading is None
            or original is None
            or discovery is None
            or discovery.backfill is True
            or reading.current_visibility is None
            or reading.current_visibility.status != "visible"
        ):
            continue
        if not report_inputs_readable_in_transaction(
            session,
            owner_id=owner_id,
            content_version_ids=(reference.content_version_id,),
            observation_ids=(reading.observation.id,),
            now=now,
        ):
            continue
        result.append(
            EventSignalContentInput(
                reference,
                reading,
                discovery.first_received_at,
                original.source_time,
                original.basis,
            )
        )
    return EventSignalContentPage(tuple(result), rows[limit - 1][0] if len(rows) > limit else None)
