"""Publishing and source-grant mutations in the caller's one business transaction."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from analysis.editorial_reading import (
    load_editorial_publication_inputs_in_transaction,
    scan_current_editorial_publication_ids_in_transaction,
)
from core.errors import ApplicationError
from events.facts import load_publication_groupings_in_transaction
from publication.projection import derive_projection, fingerprint
from publication.publication_models import (
    PublicationPolicyVersion,
    PublicationRecord,
    PublicationRepublishRun,
    PublicationRevision,
    PublicationSelectedChange,
    PublicationSourcePolicy,
    PublicationSyncState,
)
from publication.schemas import (
    ProjectionView,
    PublicationOverrideInput,
    PublishResultView,
    SourcePolicyInput,
    SourcePolicyView,
)


def require_transaction(session: Session) -> None:
    if not session.in_transaction():
        raise RuntimeError("publication requires the caller's transaction")


def policy_view(row: PublicationSourcePolicy) -> SourcePolicyView:
    return SourcePolicyView(
        source_key=row.source_key,
        revision=row.revision,
        updated_at=row.updated_at,
        **row.configuration,
    )


class PublicationService:
    def __init__(self, session: Session, *, indexing_enabled: bool = False) -> None:
        self.session, self.indexing_enabled = session, indexing_enabled

    def _lock(self, owner_id: UUID) -> None:
        require_transaction(self.session)
        self.session.execute(
            select(func.pg_advisory_xact_lock(func.hashtextextended(f"publication:{owner_id}", 0)))
        )

    def save_source_policy_in_transaction(
        self,
        *,
        owner_id: UUID,
        actor_id: UUID,
        source_key: str,
        command: SourcePolicyInput,
        now: datetime | None = None,
    ) -> SourcePolicyView:
        self._lock(owner_id)
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", source_key):
            raise ApplicationError("invalid_publication_input")
        at = now or datetime.now(UTC)
        digest = fingerprint(
            {
                "source_key": source_key,
                "actor_id": actor_id,
                "command": command.model_dump(mode="json"),
            }
        )
        replay = self.session.scalar(
            select(PublicationPolicyVersion).where(
                PublicationPolicyVersion.owner_id == owner_id,
                PublicationPolicyVersion.operation_id == command.operation_id,
            )
        )
        if replay:
            if replay.input_fingerprint != digest:
                raise ApplicationError("idempotency_conflict")
            return SourcePolicyView(
                source_key=replay.source_key,
                revision=replay.revision,
                updated_at=replay.created_at,
                **replay.configuration,
            )
        row = self.session.get(PublicationSourcePolicy, (owner_id, source_key))
        if (row.revision if row else 0) != command.expected_revision:
            raise ApplicationError("publication_revision_conflict")
        configuration = command.model_dump(
            mode="json", exclude={"operation_id", "expected_revision", "reason"}
        )
        if row is None:
            row = PublicationSourcePolicy(
                owner_id=owner_id,
                source_key=source_key,
                revision=1,
                configuration=configuration,
                updated_at=at,
            )
            self.session.add(row)
        else:
            row.revision, row.configuration, row.updated_at = row.revision + 1, configuration, at
        self.session.flush()
        self.session.add(
            PublicationPolicyVersion(
                owner_id=owner_id,
                source_key=source_key,
                revision=row.revision,
                operation_id=command.operation_id,
                actor_id=actor_id,
                input_fingerprint=digest,
                configuration=configuration,
                reason=command.reason,
                created_at=at,
            )
        )
        self.session.flush()
        return policy_view(row)

    def _state(self, owner_id: UUID, now: datetime) -> PublicationSyncState:
        state = self.session.get(PublicationSyncState, owner_id)
        if state is None:
            state = PublicationSyncState(
                owner_id=owner_id, epoch=uuid4(), sequence=0, updated_at=now
            )
            self.session.add(state)
            self.session.flush()
        return state

    def _persist(
        self,
        owner_id: UUID,
        projection: ProjectionView,
        *,
        previous: PublicationRecord | None,
        now: datetime,
        operation_id: UUID | None = None,
        actor_id: UUID | None = None,
        reason: str = "stored_evidence_reprojection",
        override: dict[str, Any] | None = None,
        operation_fingerprint: str | None = None,
    ) -> PublishResultView:
        old = ProjectionView.model_validate(previous.data) if previous else None
        # URL-only, live rights, grouping and release-time updates participate in revisions.
        same = (
            previous is not None
            and previous.input_fingerprint == projection.input_fingerprint
            and (old is not None and old.visible_after == projection.visible_after)
        )
        if same:
            assert previous is not None
            return PublishResultView(
                content_id=projection.content_id,
                changed=False,
                revision=previous.revision,
                selected=projection.selected,
                visibility=projection.visibility,
                ledger=None,
                reduced=False,
            )
        revision = previous.revision + 1 if previous else 1
        projection = projection.model_copy(update={"publication_revision": revision})
        data = projection.model_dump(mode="json")
        row = previous or PublicationRecord(
            owner_id=owner_id, content_id=projection.content_id, last_sequence=0
        )
        row.content_version_id, row.source_key, row.revision = (
            projection.content_version_id,
            projection.source_key,
            revision,
        )
        row.visibility, row.eligible, row.selected = (
            projection.visibility,
            projection.eligible,
            projection.selected,
        )
        row.visible_after, row.timeline_at, row.sort_at = (
            projection.visible_after,
            projection.timeline_at,
            projection.sort_at,
        )
        row.input_fingerprint, row.data, row.updated_at = projection.input_fingerprint, data, now
        row.override = override if override is not None else previous.override if previous else {}
        if previous is None:
            self.session.add(row)
        self.session.flush()
        self.session.add(
            PublicationRevision(
                owner_id=owner_id,
                content_id=row.content_id,
                revision=revision,
                operation_id=operation_id or uuid4(),
                actor_id=actor_id,
                input_fingerprint=operation_fingerprint or projection.input_fingerprint,
                data=data,
                reason=reason,
                created_at=now,
            )
        )
        was_selected = bool(old and old.visibility == "public" and old.selected)
        now_selected = projection.visibility == "public" and projection.selected
        operation = "upsert" if now_selected else "remove" if was_selected else None
        if operation:
            state = self._state(owner_id, now)
            state.sequence, state.updated_at = state.sequence + 1, now
            row.last_sequence = state.sequence
            self.session.add(
                PublicationSelectedChange(
                    owner_id=owner_id,
                    epoch=state.epoch,
                    sequence=state.sequence,
                    content_id=row.content_id,
                    publication_revision=revision,
                    operation=operation,
                    visible_at=projection.visible_after or now if operation == "upsert" else now,
                    changed_at=now,
                )
            )
            if projection.visible_after or operation == "remove":
                pending_release = now if operation == "remove" else projection.visible_after
                assert pending_release is not None
                for pending in self.session.scalars(
                    select(PublicationSelectedChange).where(
                        PublicationSelectedChange.owner_id == owner_id,
                        PublicationSelectedChange.content_id == row.content_id,
                        PublicationSelectedChange.visible_at > pending_release,
                    )
                ):
                    pending.visible_at = min(pending.visible_at, pending_release)
        reduced = bool(
            old
            and old.visibility == "public"
            and (
                projection.visibility != "public"
                or (old.selected and not projection.selected)
                or (old.eligible and not projection.eligible)
                or (old.body_mode == "full" and projection.body_mode != "full")
                or (old.syndicate and not projection.syndicate)
            )
        )
        self.session.flush()
        return PublishResultView(
            content_id=row.content_id,
            changed=True,
            revision=revision,
            selected=projection.selected,
            visibility=projection.visibility,
            ledger=operation,
            reduced=reduced,
        )

    def publish_in_transaction(
        self,
        *,
        owner_id: UUID,
        content_id: UUID,
        now: datetime | None = None,
        released_at: datetime | None = None,
    ) -> PublishResultView | None:
        self._lock(owner_id)
        at = now or datetime.now(UTC)
        previous = self.session.get(PublicationRecord, (owner_id, content_id))
        snapshot = load_editorial_publication_inputs_in_transaction(
            self.session, owner_id=owner_id, content_ids=(content_id,), now=at
        ).get(content_id)
        if snapshot is None:
            if previous is None:
                return None
            old = ProjectionView.model_validate(previous.data)
            projected = old.model_copy(
                update={
                    "visibility": "withdrawn",
                    "eligible": False,
                    "selected": False,
                    "indexable": False,
                    "syndicate": False,
                    "body_mode": "summary",
                    "input_fingerprint": fingerprint(
                        {"unavailable": str(old.editorial_run_id), "manual": old.manual_version}
                    ),
                }
            )
        else:
            policy = self.session.get(
                PublicationSourcePolicy, (owner_id, snapshot.material.source_key)
            )
            if policy is None:
                return None
            grouping = load_publication_groupings_in_transaction(
                self.session,
                owner_id=owner_id,
                content_versions={content_id: snapshot.material.content_version_id},
                now=at,
            ).get(content_id)
            projected = derive_projection(
                snapshot,
                policy_view(policy),
                now=at,
                previous=ProjectionView.model_validate(previous.data) if previous else None,
                override=previous.override if previous else None,
                grouping=grouping,
                released_at=released_at,
                indexing_enabled=self.indexing_enabled,
            )
            # Persist a discovery hint so a large plain-text archive cannot hide older
            # media behind the bounded scheduler page. Acceptance still checks live grants.
            from publication.media import body_presentation
            from publication.reading import _fixed_body_in_transaction

            media_count, body_sha256 = 0, None
            if projected.body_mode == "full" and projected.visibility == "public":
                body, body_format, body_sha256, attached = _fixed_body_in_transaction(
                    self.session, owner_id=owner_id, snapshot=snapshot, now=at
                )
                media_count = sum(
                    item.kind in {"image", "video"}
                    for item in body_presentation(body, body_format=body_format, media=attached)[2]
                )
            projected = projected.model_copy(
                update={
                    "media_candidate_count": media_count,
                    "input_fingerprint": fingerprint(
                        {
                            "projection": projected.input_fingerprint,
                            "body_sha256": body_sha256,
                            "media_candidate_count": media_count,
                        }
                    ),
                }
            )
            if projected.selected and projected.fact_id:
                anchors = self.session.scalars(
                    select(PublicationRecord).where(
                        PublicationRecord.owner_id == owner_id,
                        PublicationRecord.selected.is_(True),
                        PublicationRecord.visibility == "public",
                    )
                )
                times = [
                    item.sort_at
                    for item in anchors
                    if item.data.get("fact_id") == str(projected.fact_id)
                ]
                if times:
                    projected = projected.model_copy(
                        update={"sort_at": min(projected.sort_at, *times)}
                    )
        return self._persist(owner_id, projected, previous=previous, now=at)

    def override_in_transaction(
        self,
        *,
        owner_id: UUID,
        actor_id: UUID,
        content_id: UUID,
        command: PublicationOverrideInput,
        now: datetime | None = None,
    ) -> PublishResultView:
        self._lock(owner_id)
        at = now or datetime.now(UTC)
        digest = fingerprint(
            {
                "content_id": content_id,
                "actor_id": actor_id,
                "command": command.model_dump(mode="json"),
            }
        )
        replay = self.session.scalar(
            select(PublicationRevision).where(
                PublicationRevision.owner_id == owner_id,
                PublicationRevision.operation_id == command.operation_id,
            )
        )
        if replay:
            if replay.input_fingerprint != digest:
                raise ApplicationError("idempotency_conflict")
            data = ProjectionView.model_validate(replay.data)
            return PublishResultView(
                content_id=content_id,
                changed=False,
                revision=replay.revision,
                selected=data.selected,
                visibility=data.visibility,
                ledger=None,
                reduced=False,
            )
        previous = self.session.get(PublicationRecord, (owner_id, content_id))
        if previous is None:
            raise ApplicationError("resource_not_found")
        if previous.revision != command.expected_revision:
            raise ApplicationError("publication_revision_conflict")
        override = command.model_dump(
            mode="json", exclude={"operation_id", "expected_revision", "reason"}
        )
        old = ProjectionView.model_validate(previous.data)
        snapshot = load_editorial_publication_inputs_in_transaction(
            self.session, owner_id=owner_id, content_ids=(content_id,), now=at
        ).get(content_id)
        policy = self.session.get(PublicationSourcePolicy, (owner_id, previous.source_key))
        if snapshot is not None and policy is not None:
            grouping = load_publication_groupings_in_transaction(
                self.session,
                owner_id=owner_id,
                content_versions={content_id: snapshot.material.content_version_id},
                now=at,
            ).get(content_id)
            projected = derive_projection(
                snapshot,
                policy_view(policy),
                now=at,
                previous=old,
                override=override,
                grouping=grouping,
                indexing_enabled=self.indexing_enabled,
            )
        elif command.visibility == "withdrawn":
            projected = old.model_copy(
                update={
                    "visibility": "withdrawn",
                    "selected": False,
                    "eligible": False,
                    "indexable": False,
                    "syndicate": False,
                    "body_mode": "summary",
                    "input_fingerprint": fingerprint(
                        {"unavailable": str(old.editorial_run_id), "override": override}
                    ),
                }
            )
        else:
            raise ApplicationError("resource_not_found")
        return self._persist(
            owner_id,
            projected,
            previous=previous,
            now=at,
            operation_id=command.operation_id,
            actor_id=actor_id,
            reason=command.reason,
            override=override,
            operation_fingerprint=digest,
        )

    def reset_sync_epoch_in_transaction(
        self, *, owner_id: UUID, now: datetime | None = None
    ) -> UUID:
        self._lock(owner_id)
        state = self._state(owner_id, now or datetime.now(UTC))
        at = now or datetime.now(UTC)
        state.epoch, state.sequence, state.updated_at = uuid4(), 0, at
        for row in self.session.scalars(
            select(PublicationRecord)
            .where(
                PublicationRecord.owner_id == owner_id,
                PublicationRecord.selected.is_(True),
                PublicationRecord.visibility == "public",
            )
            .order_by(PublicationRecord.content_id)
        ):
            state.sequence += 1
            row.last_sequence = state.sequence
            self.session.add(
                PublicationSelectedChange(
                    owner_id=owner_id,
                    epoch=state.epoch,
                    sequence=state.sequence,
                    content_id=row.content_id,
                    publication_revision=row.revision,
                    operation="upsert",
                    visible_at=row.visible_after or at,
                    changed_at=at,
                )
            )
        self.session.flush()
        return state.epoch

    def create_republish_in_transaction(
        self,
        *,
        owner_id: UUID,
        source_key: str,
        job_id: UUID,
        operation_id: UUID,
        run_id: UUID | None = None,
        now: datetime | None = None,
    ) -> UUID:
        self._lock(owner_id)
        replay = self.session.scalar(
            select(PublicationRepublishRun).where(
                PublicationRepublishRun.owner_id == owner_id,
                PublicationRepublishRun.operation_id == operation_id,
            )
        )
        if replay:
            if replay.source_key != source_key or replay.job_id != job_id:
                raise ApplicationError("idempotency_conflict")
            return replay.id
        policy = self.session.get(PublicationSourcePolicy, (owner_id, source_key))
        if policy is None:
            raise ApplicationError("resource_not_found")
        at = now or datetime.now(UTC)
        run = PublicationRepublishRun(
            id=run_id or uuid4(),
            owner_id=owner_id,
            source_key=source_key,
            policy_revision=policy.revision,
            job_id=job_id,
            operation_id=operation_id,
            status="queued",
            after_content_id=None,
            processed_count=0,
            failure_code=None,
            created_at=at,
            updated_at=at,
        )
        self.session.add(run)
        self.session.flush()
        return run.id

    def republish_page_in_transaction(
        self, *, owner_id: UUID, run_id: UUID, limit: int = 100, now: datetime | None = None
    ) -> dict[str, Any]:
        self._lock(owner_id)
        if not 1 <= limit <= 1000:
            raise ValueError("republish page must be bounded")
        run = self.session.scalar(
            select(PublicationRepublishRun)
            .where(
                PublicationRepublishRun.owner_id == owner_id, PublicationRepublishRun.id == run_id
            )
            .with_for_update()
        )
        if run is None:
            raise ApplicationError("resource_not_found")
        if run.status in {"completed", "cancelled", "failed"}:
            return {
                "status": run.status,
                "processed": run.processed_count,
                "after": run.after_content_id,
            }
        at = now or datetime.now(UTC)
        policy = self.session.get(PublicationSourcePolicy, (owner_id, run.source_key))
        if policy is None or policy.revision != run.policy_revision:
            run.status, run.failure_code, run.updated_at = (
                "failed",
                "publication_policy_changed",
                at,
            )
            self.session.flush()
            return {
                "status": run.status,
                "processed": run.processed_count,
                "after": run.after_content_id,
            }
        query = (
            select(PublicationRecord.content_id)
            .where(
                PublicationRecord.owner_id == owner_id,
                PublicationRecord.source_key == run.source_key,
            )
            .order_by(PublicationRecord.content_id)
            .limit(limit + 1)
        )
        if run.after_content_id:
            query = query.where(PublicationRecord.content_id > run.after_content_id)
        existing = tuple(self.session.scalars(query))
        candidates = scan_current_editorial_publication_ids_in_transaction(
            self.session,
            owner_id=owner_id,
            limit=min(limit + 1, 1000),
            after=run.after_content_id,
            source_key=run.source_key,
        )
        ids = tuple(sorted(set(existing) | set(candidates.content_ids)))
        has_more = len(ids) > limit or candidates.next_after is not None
        run.status, run.updated_at = "running", at
        for content_id in ids[:limit]:
            self.publish_in_transaction(owner_id=owner_id, content_id=content_id, now=at)
            run.after_content_id, run.processed_count = content_id, run.processed_count + 1
        if not has_more:
            run.status = "completed"
        self.session.flush()
        return {
            "status": run.status,
            "processed": run.processed_count,
            "after": run.after_content_id,
        }

    def finish_republish_in_transaction(
        self,
        *,
        owner_id: UUID,
        run_id: UUID,
        status: str,
        failure_code: str | None = None,
        now: datetime | None = None,
    ) -> None:
        self._lock(owner_id)
        if status not in {"failed", "cancelled"}:
            raise ApplicationError("invalid_publication_input")
        run = self.session.scalar(
            select(PublicationRepublishRun)
            .where(
                PublicationRepublishRun.owner_id == owner_id, PublicationRepublishRun.id == run_id
            )
            .with_for_update()
        )
        if run is None:
            raise ApplicationError("resource_not_found")
        if run.status not in {"completed", "cancelled"}:
            run.status, run.failure_code, run.updated_at = (
                status,
                failure_code,
                now or datetime.now(UTC),
            )
            self.session.flush()
