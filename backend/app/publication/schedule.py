"""Bounded projection reconciliation through existing Job and rebuild checkpoints."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid5

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from jobs.schemas import JobAcceptanceInput, JobObservationContext
from jobs.services import JobService, load_job_id_for_operation_in_transaction
from publication.publication_models import PublicationRepublishRun, PublicationSourcePolicy
from publication.services import PublicationService

_NAMESPACE = UUID("b0525f8a-8baf-4d04-bf9a-cc59df6b2b08")
_INTERVAL = 300


def enqueue_due_publication_in_transaction(
    session: Session, *, now: datetime, enabled: bool = True, limit: int = 20
) -> int:
    if not session.in_transaction() or now.utcoffset() is None or not 1 <= limit <= 100:
        raise ValueError("publication scheduling needs an aware bounded caller transaction")
    if not enabled:
        return 0
    last = (
        select(func.max(PublicationRepublishRun.created_at))
        .where(
            PublicationRepublishRun.owner_id == PublicationSourcePolicy.owner_id,
            PublicationRepublishRun.source_key == PublicationSourcePolicy.source_key,
        )
        .scalar_subquery()
    )
    pending = exists().where(
        PublicationRepublishRun.owner_id == PublicationSourcePolicy.owner_id,
        PublicationRepublishRun.source_key == PublicationSourcePolicy.source_key,
        PublicationRepublishRun.status.in_(("queued", "running")),
    )
    policies = tuple(
        session.scalars(
            select(PublicationSourcePolicy)
            .where(~pending, or_(last.is_(None), last <= now - timedelta(seconds=_INTERVAL)))
            .order_by(
                last.asc().nulls_first(),
                PublicationSourcePolicy.owner_id,
                PublicationSourcePolicy.source_key,
            )
            .limit(limit)
        )
    )
    window = datetime.fromtimestamp(int(now.timestamp()) // _INTERVAL * _INTERVAL, UTC)
    count = 0
    for policy in policies:
        service = PublicationService(session)
        service._lock(policy.owner_id)
        # The candidate query precedes the owner lock. Another scheduler may have
        # accepted a newer window or changed the policy while this one waited.
        fresh_policy = session.get(
            PublicationSourcePolicy, (policy.owner_id, policy.source_key), populate_existing=True
        )
        if fresh_policy is None:
            continue
        policy = fresh_policy
        previous_run = session.scalar(
            select(PublicationRepublishRun)
            .where(
                PublicationRepublishRun.owner_id == policy.owner_id,
                PublicationRepublishRun.source_key == policy.source_key,
            )
            .order_by(PublicationRepublishRun.created_at.desc())
            .limit(1)
        )
        if previous_run is not None and (
            previous_run.status in {"queued", "running"}
            or previous_run.created_at > now - timedelta(seconds=_INTERVAL)
        ):
            continue
        operation = uuid5(
            _NAMESPACE, f"{policy.owner_id}:{policy.source_key}:{policy.revision}:{window}"
        )
        if (
            load_job_id_for_operation_in_transaction(
                session, owner_id=policy.owner_id, operation_id=operation
            )
            is not None
        ):
            continue
        run_id = uuid5(operation, f"publication:{policy.source_key}")
        job = JobService(session, clock=lambda: now).accept_in_transaction(
            owner_id=policy.owner_id,
            command=JobAcceptanceInput(
                operation_id=operation,
                kind="publication.republish",
                observation=JobObservationContext(
                    configuration_ref=f"publication-source:{policy.source_key}",
                    configuration_version=policy.revision,
                ),
                scope={
                    "republish_run_id": str(run_id),
                    "source_key": policy.source_key,
                    "policy_revision": policy.revision,
                },
            ),
        )
        service.create_republish_in_transaction(
            owner_id=policy.owner_id,
            source_key=policy.source_key,
            job_id=job.id,
            operation_id=operation,
            run_id=run_id,
            now=now,
        )
        count += 1
    return count


def enqueue_due_media_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    now: datetime,
    enabled: bool = False,
    allow_external_requests: bool = False,
    limit: int = 20,
) -> int:
    """Admit only untouched licensed fixed-body candidates; terminal/unknown runs never retry."""
    from core.errors import ApplicationError
    from evidence.services import load_source_access_readiness
    from publication.media_mirror_models import PublicationMediaRun
    from publication.media_mirror_schemas import MediaMirrorInput
    from publication.media_mirror_services import (
        PublicationMediaService,
        require_media_grant_in_transaction,
    )
    from publication.publication_models import PublicationRecord
    from sources.contracts import SourceCapability

    if not session.in_transaction() or now.utcoffset() is None or not 1 <= limit <= 100:
        raise ValueError("media scheduler requires an aware bounded caller transaction")
    if not enabled or not allow_external_requests:
        return 0
    ready = load_source_access_readiness(session, owner_id=owner_id, now=now)
    sources = {
        key
        for (key, capability), allowed in ready.items()
        if allowed and capability is SourceCapability.PAGE_CONTENT
    }
    if not sources:
        return 0
    mirrored = exists().where(
        PublicationMediaRun.owner_id == owner_id,
        PublicationMediaRun.content_id == PublicationRecord.content_id,
        PublicationMediaRun.content_version_id == PublicationRecord.content_version_id,
        PublicationMediaRun.policy_revision == PublicationSourcePolicy.revision,
    )
    query = (
        select(PublicationRecord, PublicationSourcePolicy.revision)
        .join(
            PublicationSourcePolicy,
            (PublicationSourcePolicy.owner_id == PublicationRecord.owner_id)
            & (PublicationSourcePolicy.source_key == PublicationRecord.source_key),
        )
        .where(
            PublicationRecord.owner_id == owner_id,
            PublicationRecord.source_key.in_(sources),
            PublicationRecord.visibility == "public",
            PublicationRecord.selected,
            PublicationRecord.eligible,
            PublicationRecord.visible_after <= now,
            PublicationRecord.data["body_mode"].as_string() == "full",
            PublicationRecord.data["media_candidate_count"].as_integer() > 0,
            ~mirrored,
        )
        .order_by(PublicationRecord.content_id)
    )

    def due_records() -> Iterator[tuple[PublicationRecord, int]]:
        after = None
        while True:
            page_query = query.where(PublicationRecord.content_id > after) if after else query
            rows = session.execute(page_query.limit(500)).all()
            yield from ((record, revision) for record, revision in rows)
            if len(rows) < 500:
                return
            after = rows[-1][0].content_id

    count = 0
    for record, revision in due_records():
        if count >= limit:
            break
        try:
            _, candidates, _ = require_media_grant_in_transaction(
                session,
                owner_id=owner_id,
                content_id=record.content_id,
                version_id=record.content_version_id,
                policy_revision=revision,
                now=now,
            )
            if not candidates:
                continue
            operation_id = uuid5(
                _NAMESPACE,
                f"media:{owner_id}:{record.content_id}:{record.content_version_id}:{revision}",
            )
            result = PublicationMediaService(session, enabled=True).request_in_transaction(
                owner_id=owner_id,
                content_id=record.content_id,
                command=MediaMirrorInput(
                    operation_id=operation_id,
                    content_version_id=record.content_version_id,
                    policy_revision=revision,
                ),
                now=now,
            )
            count += not result.replayed
        except ApplicationError as error:
            if error.code not in {"publication_revision_conflict", "invalid_publication_input"}:
                raise
    return count
