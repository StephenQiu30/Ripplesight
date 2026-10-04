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
)
from content.observation_context import (
    load_observation_contexts_in_transaction,
    load_observation_visibilities_in_transaction,
)
from content.observation_reading import readable_observation_groups_in_transaction
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
    if len(references) > 2000:
        raise ValueError("event reading allows at most 2000 fixed references")
    if len(references) > 1 and (
        len({(ref.content_id, ref.content_version_id) for ref in references}) != len(references)
        or any(ref.legacy_strict for ref in references)
    ):
        combined: dict[EventContentReadReference, EventContentReadView] = {}
        for reference in references:
            combined.update(
                load_event_member_content_in_transaction(
                    session, owner_id=owner_id, references=(reference,), now=now
                )
            )
        return combined
    requested_reference = references[0]
    if requested_reference.legacy_strict:
        from content.version_inputs import legacy_content_versions_readable_in_transaction

        if not legacy_content_versions_readable_in_transaction(
            session,
            owner_id=owner_id,
            content_version_ids=(requested_reference.content_version_id,),
            now=now,
        ):
            return {}
    reference_keys = {ref: str(index) for index, ref in enumerate(references)}
    supplied_groups = {
        reference_keys[ref]: ref.input_observation_ids
        for ref in references
        if ref.input_observation_ids
    }
    supplied_closures = (
        readable_observation_groups_in_transaction(
            session, owner_id=owner_id, observation_groups=supplied_groups, now=now
        )
        if supplied_groups
        else {}
    )
    references = tuple(
        ref
        for ref in references
        if not ref.input_observation_ids
        or (
            supplied_closures.get(reference_keys[ref])
            == tuple(sorted(ref.input_observation_ids, key=str))
            and (ref.observation_id is None or ref.observation_id in ref.input_observation_ids)
        )
    )
    if not references:
        return {}
    by_pair = {(ref.content_id, ref.content_version_id): ref for ref in references}
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
    }
    if not fixed:
        return {}
    statement = select(ContentObservation)
    if all(ref.observation_id is not None for ref in references):
        statement = statement.where(
            ContentObservation.id.in_({ref.observation_id for ref in references})
        )
    observations = session.scalars(
        statement.where(
            ContentObservation.owner_id == owner_id,
            ContentObservation.content_version_id.in_({version_id for _, version_id in fixed}),
            ContentObservation.id.in_(readable),
        ).order_by(
            ContentObservation.observed_at.desc(),
            ContentObservation.received_at.desc(),
            ContentObservation.id.desc(),
        )
    ).all()
    contexts = load_observation_contexts_in_transaction(
        session, owner_id=owner_id, observation_ids={obs.id for obs in observations}
    )
    roots_without_proof = {
        str(obs.id): (obs.id,)
        for obs in observations
        if obs.content_version_id is not None
        and (obs.content_id, obs.content_version_id) in by_pair
        if not by_pair[(obs.content_id, obs.content_version_id)].input_observation_ids
    }
    root_permissions = {}
    items = tuple(roots_without_proof.items())
    for offset in range(0, len(items), 2000):
        root_permissions.update(
            readable_observation_groups_in_transaction(
                session,
                owner_id=owner_id,
                observation_groups=dict(items[offset : offset + 2000]),
                now=now,
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
        requested_reference = by_pair[pair]
        if (
            requested_reference.observation_id is not None
            and observation.id != requested_reference.observation_id
        ):
            continue
        if requested_reference.expected_source_key is not None:
            actual = contexts.get(observation.id)
            if (
                actual is None
                or actual.source_key != requested_reference.expected_source_key
                or (
                    requested_reference.observation_source_key
                    != (actual.source_key if actual.input_basis is not None else None)
                )
            ):
                continue
        if not requested_reference.input_observation_ids and not root_permissions.get(
            str(observation.id)
        ):
            continue
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
        by_comment = {
            (ref.content_id, ref.representative_comment_id): ref
            for ref in references
            if ref.representative_comment_id is not None
        }
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
        comment_permissions = {}
        for offset in range(0, len(comment_rows), 2000):
            comment_permissions.update(
                readable_observation_groups_in_transaction(
                    session,
                    owner_id=owner_id,
                    observation_groups={
                        str(obs.id): (obs.id,) for _, _, obs in comment_rows[offset : offset + 2000]
                    },
                    now=now,
                )
            )
        for thread, version, observation in comment_rows:
            requested_reference = by_comment[(thread.post_content_id, thread.content_id)]
            if (
                requested_reference.representative_comment_observation_id is not None
                and observation.id != requested_reference.representative_comment_observation_id
            ):
                continue
            if (
                requested_reference.input_observation_ids
                and observation.id not in requested_reference.input_observation_ids
            ):
                continue
            if not comment_permissions.get(str(observation.id)):
                continue
            comments.setdefault(
                (thread.post_content_id, thread.content_id), (thread, version, observation)
            )

    versions = {version.id: version for _, version, _ in selected.values()}
    versions.update({version.id: version for _, version, _ in comments.values()})
    version_views = _version_views(session, owner_id=owner_id, versions=versions, readable=readable)
    visibilities = load_observation_visibilities_in_transaction(
        session,
        owner_id=owner_id,
        contexts={
            obs.id: contexts[obs.id] for _, _, obs in selected.values() if obs.id in contexts
        },
    )
    result: dict[EventContentReadReference, EventContentReadView] = {}
    for reference in references:
        selection = selected.get((reference.content_id, reference.content_version_id))
        if selection is None:
            continue
        record, version, observation = selection
        actual = contexts.get(observation.id)
        if actual is None:
            continue
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
            source_key=actual.source_key,
            object_type=cast(Literal["post", "comment", "webpage"], record.object_type),
            native_scope=actual.native_scope,
            collection_scope=(
                collection_scopes[observation.job_id].selector_ref
                if observation.job_id in collection_scopes
                and collection_scopes[observation.job_id].source_key == actual.source_key
                else None
            ),
            external_id=actual.external_id,
            identity_basis=cast(Literal["guid", "url_fallback"] | None, actual.identity_basis),
            observation=_observation_view(observation, version_views[version.id]),
            current_visibility=ContentVisibilityView.model_validate(selected_visibility)
            if (selected_visibility := visibilities.get(observation.id))
            else None,
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
