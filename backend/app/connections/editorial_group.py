"""Frozen group DTO admission over the existing source profiles and run receipts."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Literal, cast
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from connections.editorial_models import (
    EditorialSourceProfile,
    EditorialSourceRun,
    EditorialSourceVersion,
)
from connections.editorial_schemas import (
    EditorialGroupBacklogMember,
    EditorialGroupBacklogReviewInput,
    EditorialGroupBacklogReviewResult,
    EditorialGroupBacklogView,
)
from connections.editorial_services import (
    EditorialSourceService,
    Guard,
    PreparedEditorialRun,
)
from core.errors import ApplicationError
from evidence.services import RetentionPolicyUnavailableError, SourceAccessUnavailableError
from jobs.editorial_member import (
    load_active_editorial_profile_ids_in_transaction,
    load_editorial_group_manifest_in_transaction,
)
from jobs.editorial_schemas import EditorialGroupManifest, EditorialGroupMember
from operations.services import (
    accept_audit_in_transaction,
    complete_audit_in_transaction,
    load_completed_audit_in_transaction,
)
from sources.adapters.editorial_x import shard_eligible
from sources.editorial_schemas import EditorialCursor, EditorialProfileView, fingerprint


def _cursor_json(cursor: EditorialCursor) -> str:
    return cursor.model_dump_json(exclude={"x_backlog": {"__all__": {"group_manifest_json"}}})


def _member(
    profile: EditorialProfileView, cursor: EditorialCursor, handle: str
) -> EditorialGroupMember:
    return EditorialGroupMember(
        profile_id=profile.id,
        source_key=profile.source_key,
        configuration_version=profile.configuration_version,
        revision=profile.revision,
        policy_version=profile.policy_version,
        configuration_sha256=fingerprint(profile.configuration.model_dump(mode="json")).hex(),
        handle=handle,
        cursor_json=_cursor_json(cursor),
    )


def require_editorial_group_admission_in_transaction(
    session: Session,
    *,
    manifest: EditorialGroupManifest,
    job_id: UUID,
    guard: Guard | None,
    now: datetime,
    require_running: bool = False,
) -> None:
    if not session.in_transaction():
        raise RuntimeError("group admission requires caller transaction")
    frozen = load_editorial_group_manifest_in_transaction(
        session, owner_id=manifest.owner_id, job_id=job_id
    )
    if frozen != manifest or (guard is not None and not guard(session, manifest.owner_id, job_id)):
        raise ApplicationError("editorial_version_conflict")
    service = EditorialSourceService(session, clock=lambda: now)
    for member in sorted(manifest.members, key=lambda m: str(m.profile_id)):
        p = service._profile(manifest.owner_id, member.profile_id, lock=True)
        v = service._version(p)
        profile = service._view(p)
        query = re.fullmatch(
            r"from:([A-Za-z0-9_]{1,15})(?:\s+-(?:filter:replies|is:reply))?",
            profile.configuration.query or "",
            re.IGNORECASE,
        )
        if (
            not profile.enabled
            or profile.configuration_version != member.configuration_version
            or profile.revision != member.revision
            or profile.policy_version != member.policy_version
            or profile.connection_id != manifest.connection_id
            or profile.connection_version != manifest.connection_version
            or profile.participation_mode != manifest.participation_mode
            or profile.source_key != member.source_key
            or profile.configuration.kind != "x_search"
            or profile.configuration.search_type != "Latest"
            or query is None
            or query.group(1).casefold() != member.handle.casefold()
            or fingerprint(profile.configuration.model_dump(mode="json")).hex()
            != member.configuration_sha256
        ):
            raise ApplicationError("editorial_version_conflict")
        service._require_ready(p, v, now)
        if require_running:
            run = session.scalar(
                select(EditorialSourceRun)
                .where(
                    EditorialSourceRun.owner_id == manifest.owner_id,
                    EditorialSourceRun.profile_id == p.id,
                    EditorialSourceRun.job_id == job_id,
                )
                .with_for_update()
            )
            if run is None or run.status != "running":
                raise ApplicationError("editorial_version_conflict")


def hold_editorial_group_runs_in_transaction(
    session: Session,
    *,
    manifest: EditorialGroupManifest,
    job_id: UUID,
    guard: Guard,
    now: datetime,
    reason: str,
) -> None:
    """Retain uncertain receipts after permission changes; never publish their material."""
    if not session.in_transaction() or not guard(session, manifest.owner_id, job_id):
        raise ApplicationError("editorial_version_conflict")
    for run in session.scalars(
        select(EditorialSourceRun)
        .where(
            EditorialSourceRun.owner_id == manifest.owner_id,
            EditorialSourceRun.job_id == job_id,
            EditorialSourceRun.profile_id.in_(m.profile_id for m in manifest.members),
            EditorialSourceRun.status.in_(("running", "staged")),
        )
        .with_for_update()
    ):
        run.status, run.failure_code, run.updated_at = "unknown", reason, now


def begin_editorial_group_runs_in_transaction(
    session: Session,
    *,
    manifest: EditorialGroupManifest,
    job_id: UUID,
    operation_id: UUID,
    guard: Guard | None,
    now: datetime,
) -> tuple[PreparedEditorialRun, ...]:
    require_editorial_group_admission_in_transaction(
        session, manifest=manifest, job_id=job_id, guard=guard, now=now
    )
    service = EditorialSourceService(session, clock=lambda: now)
    return tuple(
        service._begin_run_in_transaction(
            owner_id=manifest.owner_id,
            profile_id=m.profile_id,
            configuration_version=m.configuration_version,
            revision=m.revision,
            job_id=job_id,
            operation_id=operation_id,
            guard=guard,
        )
        for m in manifest.members
    )


def freeze_due_editorial_groups_in_transaction(
    session: Session, *, now: datetime, limit: int = 200
) -> tuple[EditorialGroupManifest, ...]:
    if not session.in_transaction():
        raise RuntimeError("group due reads require caller transaction")
    service = EditorialSourceService(session, clock=lambda: now)
    groups = defaultdict(list)
    active: dict[UUID, frozenset[UUID]] = {}
    cursors: dict[UUID, EditorialCursor] = {}
    due_at: dict[UUID, datetime] = {}
    candidates: dict[UUID, tuple[UUID, EditorialProfileView]] = {}
    rows = session.execute(
        select(EditorialSourceProfile.id, EditorialSourceProfile.owner_id)
        .join(
            EditorialSourceVersion,
            (EditorialSourceVersion.profile_id == EditorialSourceProfile.id)
            & (EditorialSourceVersion.owner_id == EditorialSourceProfile.owner_id)
            & (EditorialSourceVersion.version == EditorialSourceProfile.current_version),
        )
        .where(
            EditorialSourceProfile.enabled.is_(True),
            EditorialSourceVersion.kind == "x_search",
            or_(
                EditorialSourceProfile.next_fetch_at.is_(None),
                EditorialSourceProfile.next_fetch_at <= now + timedelta(seconds=30),
            ),
        )
        .order_by(
            EditorialSourceProfile.next_fetch_at.asc().nullsfirst(), EditorialSourceProfile.id
        )
        .limit(limit)
    ).all()
    for profile_id, owner_id in rows:
        active.setdefault(
            owner_id, load_active_editorial_profile_ids_in_transaction(session, owner_id=owner_id)
        )
        if profile_id in active[owner_id]:
            continue
        p = service._profile(owner_id, profile_id, lock=True)
        profile = service._view(p)
        cursor = EditorialCursor.model_validate(p.cursor)
        if (
            service._has_unresolved(p)
            or not cursor.last_tweet_id
            or cursor.initialized_at is None
            or profile.configuration.search_type != "Latest"
            or profile.connection_id is None
            or profile.connection_version is None
        ):
            continue
        try:
            service._require_ready(p, service._version(p), now)
        except (ApplicationError, SourceAccessUnavailableError, RetentionPolicyUnavailableError):
            continue
        candidates[p.id] = (owner_id, profile)
        cursors[p.id] = cursor
        due_at[p.id] = p.next_fetch_at or p.created_at
        if cursor.x_backlog:
            continue
        groups[
            (
                owner_id,
                profile.connection_id,
                profile.connection_version,
                profile.participation_mode,
            )
        ].append(profile)
    results: list[EditorialGroupManifest] = []
    consumed: set[UUID] = set()
    seen_backlogs: set[str] = set()
    for profile_id, (owner_id, _profile) in candidates.items():
        for gap in cursors[profile_id].x_backlog:
            if gap.group_manifest_json is None or gap.state == "held":
                continue
            original = EditorialGroupManifest.model_validate_json(gap.group_manifest_json)
            if original.sha256 in seen_backlogs:
                continue
            seen_backlogs.add(original.sha256)
            resume_members: list[EditorialGroupMember] = []
            coherent = original.owner_id == owner_id
            for frozen in original.members:
                current = candidates.get(frozen.profile_id)
                if current is None or frozen.profile_id in consumed:
                    coherent = False
                    break
                actual_owner, actual = current
                if (
                    actual_owner != owner_id
                    or actual.configuration_version != frozen.configuration_version
                    or actual.policy_version != frozen.policy_version
                    or actual.connection_id != original.connection_id
                    or actual.connection_version != original.connection_version
                    or actual.participation_mode != original.participation_mode
                    or fingerprint(actual.configuration.model_dump(mode="json")).hex()
                    != frozen.configuration_sha256
                ):
                    coherent = False
                    break
                resume_members.append(_member(actual, cursors[actual.id], frozen.handle))
            if coherent:
                updated = original.model_copy(
                    update={
                        "members": tuple(resume_members),
                        "scheduled_for_at": max(due_at[m.profile_id] for m in resume_members),
                    }
                )
                # Recompute only the new request's waterline. The old token keeps
                # its original stop_at_id, query and members in each source cursor.
                resume_shards = shard_eligible(
                    tuple(candidates[m.profile_id][1] for m in resume_members), cursors
                )
                if len(resume_shards) == 1:
                    updated = updated.model_copy(update={"since_id": resume_shards[0].since_id})
                results.append(updated)
                consumed.update(m.profile_id for m in resume_members)
    for (owner, connection, version, mode), profiles in groups.items():
        remaining = tuple(p for p in profiles if p.id not in consumed)
        for shard in shard_eligible(remaining, cursors):
            if len(shard.members) < 2:
                continue
            by_id = {p.id: p for p in remaining}
            members = tuple(
                _member(by_id[i], cursors[i], handle)
                for i, handle in zip(shard.members, shard.handles, strict=True)
            )
            if len({m.handle.casefold() for m in members}) != len(members):
                continue
            results.append(
                EditorialGroupManifest(
                    owner_id=owner,
                    connection_id=connection,
                    connection_version=version,
                    participation_mode=mode,
                    query=shard.query,
                    since_id=shard.since_id,
                    scheduled_for_at=max(due_at[m.profile_id] for m in members),
                    members=members,
                )
            )
    return tuple(results)


def _backlog_manifests(session: Session, owner_id: UUID) -> dict[str, EditorialGroupManifest]:
    manifests: dict[str, EditorialGroupManifest] = {}
    for cursor_json in session.scalars(
        select(EditorialSourceProfile.cursor)
        .where(EditorialSourceProfile.owner_id == owner_id)
        .order_by(EditorialSourceProfile.id)
        .limit(200)
    ):
        for gap in EditorialCursor.model_validate(cursor_json).x_backlog:
            if gap.group_manifest_json is not None:
                original = EditorialGroupManifest.model_validate_json(gap.group_manifest_json)
                if original.owner_id == owner_id:
                    manifests.setdefault(original.sha256, original)
    return manifests


def _backlog_member(profile: EditorialProfileView) -> EditorialGroupBacklogMember:
    return EditorialGroupBacklogMember(
        profile_id=profile.id,
        source_key=profile.source_key,
        name=profile.name,
        configuration_version=profile.configuration_version,
        revision=profile.revision,
        enabled=profile.enabled,
    )


def list_editorial_group_backlogs_in_transaction(
    session: Session, *, owner_id: UUID
) -> tuple[EditorialGroupBacklogView, ...]:
    if not session.in_transaction():
        raise RuntimeError("group backlog reads require caller transaction")
    service = EditorialSourceService(session)
    result = []
    for group_hash, original in tuple(_backlog_manifests(session, owner_id).items())[:100]:
        members = []
        state = "pending"
        for frozen in original.members:
            p = service._profile(owner_id, frozen.profile_id)
            profile = service._view(p)
            members.append(_backlog_member(profile))
            cursor = EditorialCursor.model_validate(p.cursor)
            if (
                not profile.enabled
                or profile.configuration_version != frozen.configuration_version
                or profile.policy_version != frozen.policy_version
                or profile.connection_id != original.connection_id
                or profile.connection_version != original.connection_version
                or profile.participation_mode != original.participation_mode
                or fingerprint(profile.configuration.model_dump(mode="json")).hex()
                != frozen.configuration_sha256
            ):
                state = "blocked_configuration"
            elif state != "blocked_configuration" and any(
                gap.state == "held"
                and gap.group_manifest_json is not None
                and EditorialGroupManifest.model_validate_json(gap.group_manifest_json).sha256
                == group_hash
                for gap in cursor.x_backlog
            ):
                state = "held"
        result.append(
            EditorialGroupBacklogView(
                group_sha256=group_hash,
                query=original.query,
                state=cast(Literal["pending", "held", "blocked_configuration"], state),
                members=tuple(members),
            )
        )
    return tuple(result)


def review_editorial_group_backlog_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    command: EditorialGroupBacklogReviewInput,
    now: datetime,
) -> EditorialGroupBacklogReviewResult:
    if not session.in_transaction() or now.utcoffset() is None:
        raise RuntimeError("group backlog review requires aware caller transaction")
    _audit, replayed = accept_audit_in_transaction(
        session,
        owner_id=owner_id,
        operation_id=command.operation_id,
        action="editorial_source.group_backlog_review",
        target_ref=f"editorial-group:{command.group_sha256}",
        reason=command.reason,
        payload=command.model_dump(mode="json"),
        now=now,
        before_state={
            "expected_members": [m.model_dump(mode="json") for m in command.expected_members]
        },
    )
    if replayed:
        frozen = load_completed_audit_in_transaction(
            session, owner_id=owner_id, operation_id=command.operation_id
        )
        if frozen is not None:
            return EditorialGroupBacklogReviewResult.model_validate(frozen)
    original = _backlog_manifests(session, owner_id).get(command.group_sha256)
    if original is None or {m.profile_id for m in original.members} != {
        m.profile_id for m in command.expected_members
    }:
        raise ApplicationError("editorial_version_conflict")
    active = load_active_editorial_profile_ids_in_transaction(session, owner_id=owner_id)
    service = EditorialSourceService(session, clock=lambda: now)
    members = []
    for expected in sorted(command.expected_members, key=lambda m: str(m.profile_id)):
        p = service._profile(owner_id, expected.profile_id, lock=True)
        if (
            p.current_version != expected.configuration_version
            or p.revision != expected.revision
            or p.id in active
            or service._has_unresolved(p)
        ):
            raise ApplicationError("editorial_version_conflict")
        cursor = EditorialCursor.model_validate(p.cursor)
        gaps = tuple(
            g
            for g in cursor.x_backlog
            if g.group_manifest_json is not None
            and EditorialGroupManifest.model_validate_json(g.group_manifest_json).sha256
            == command.group_sha256
        )
        if not gaps:
            raise ApplicationError("editorial_version_conflict")
        lower = min(int(g.stop_at_id or original.since_id) for g in gaps)
        p.cursor = cursor.model_copy(
            update={
                "last_tweet_id": str(min(int(cursor.last_tweet_id or lower), lower)),
                "x_backlog": tuple(g for g in cursor.x_backlog if g not in gaps),
            }
        ).model_dump(mode="json")
        p.revision += 1
        p.next_fetch_at, p.updated_at, p.health = now, now, "unknown"
        members.append(_backlog_member(service._view(p)))
    result = EditorialGroupBacklogReviewResult(
        group_sha256=command.group_sha256, members=tuple(members)
    )
    complete_audit_in_transaction(
        session,
        owner_id=owner_id,
        operation_id=command.operation_id,
        after_state=result.model_dump(mode="json"),
        now=now,
    )
    return result
