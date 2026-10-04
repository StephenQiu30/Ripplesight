"""Topic source availability reads without importing content or running collectors."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from connections.editorial_models import (
    EditorialSourceProfile,
    EditorialSourceRun,
    EditorialSourceVersion,
)
from connections.editorial_rsshub import (
    require_editorial_profile_ready_in_transaction,
    require_editorial_rsshub_execution_in_transaction,
)
from core.errors import ApplicationError
from evidence.services import RetentionPolicyUnavailableError, SourceAccessUnavailableError
from sources.editorial_schemas import EditorialSourceConfiguration


@dataclass(frozen=True, slots=True)
class EditorialTopicSourceAvailability:
    profile_id: UUID
    name: str
    configuration_version: int
    enabled: bool
    query_mode: str
    text_scope: str
    selectable: bool
    reason: str | None
    last_ok_at: datetime | None
    interval_minutes: int
    source_key: str


def _availability(
    session: Session,
    profile: EditorialSourceProfile,
    version: EditorialSourceVersion,
    now: datetime,
) -> EditorialTopicSourceAvailability:
    config = EditorialSourceConfiguration.model_validate(version.configuration)
    mode = config.rsshub.query_mode if config.rsshub else "feed_local_filter"
    scope = config.rsshub.text_scope if config.rsshub else "excerpt"
    reason: str | None = None
    try:
        if not profile.enabled:
            raise ApplicationError("editorial_source_disabled")
        if config.kind in {"x_search", "mp_account", "external"} or (config.url or "").startswith(
            "https://r.jina.ai/"
        ):
            raise ApplicationError(
                "editorial_source_unavailable",
                context={
                    "reason": "free_only_paid_source"
                    if config.kind != "external"
                    else "external_ingest_only"
                },
            )
        if version.participation_mode != "editorial" or mode == "hotlist":
            raise ApplicationError(
                "editorial_source_unavailable",
                context={"reason": "editorial_participation_required"},
            )
        if (
            session.scalar(
                select(EditorialSourceRun.id)
                .where(
                    EditorialSourceRun.owner_id == profile.owner_id,
                    EditorialSourceRun.profile_id == profile.id,
                    EditorialSourceRun.status == "unknown",
                )
                .limit(1)
            )
            is not None
        ):
            raise ApplicationError(
                "editorial_source_unavailable", context={"reason": "source_run_review_required"}
            )
        require_editorial_profile_ready_in_transaction(
            session, profile=profile, version=version, now=now
        )
        if config.rsshub:
            require_editorial_rsshub_execution_in_transaction(
                session,
                owner_id=profile.owner_id,
                profile_id=profile.id,
                configuration_version=version.version,
                revision=profile.revision,
                now=now,
            )
    except ApplicationError as error:
        reason = str(error.context.get("reason") or error.code)
    except (SourceAccessUnavailableError, RetentionPolicyUnavailableError):
        reason = "source_policy_unavailable"
    return EditorialTopicSourceAvailability(
        profile_id=profile.id,
        name=profile.name,
        configuration_version=version.version,
        enabled=profile.enabled,
        query_mode=mode,
        text_scope=scope,
        selectable=reason is None,
        reason=reason,
        last_ok_at=profile.last_ok_at,
        interval_minutes=version.interval_minutes,
        source_key=profile.source_key,
    )


def list_editorial_topic_sources_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    now: datetime,
    limit: int = 200,
) -> tuple[EditorialTopicSourceAvailability, ...]:
    if not session.in_transaction() or now.utcoffset() is None or not 1 <= limit <= 200:
        raise ValueError("topic source read requires an aware bounded caller transaction")
    rows = session.execute(
        select(EditorialSourceProfile, EditorialSourceVersion)
        .join(
            EditorialSourceVersion,
            (EditorialSourceVersion.owner_id == EditorialSourceProfile.owner_id)
            & (EditorialSourceVersion.profile_id == EditorialSourceProfile.id)
            & (EditorialSourceVersion.version == EditorialSourceProfile.current_version),
        )
        .where(EditorialSourceProfile.owner_id == owner_id)
        .order_by(
            EditorialSourceProfile.name,
            EditorialSourceProfile.id,
        )
        .limit(limit)
    ).all()
    return tuple(_availability(session, profile, version, now) for profile, version in rows)


def require_editorial_topic_profiles_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    profile_ids: tuple[UUID, ...],
    now: datetime,
) -> None:
    if not session.in_transaction() or now.utcoffset() is None or len(profile_ids) > 200:
        raise ValueError("topic source admission requires an aware bounded caller transaction")
    if len(set(profile_ids)) != len(profile_ids):
        raise ApplicationError("invalid_editorial_input")
    from connections.editorial_rsshub import load_current_editorial_profile_in_transaction

    for profile_id in profile_ids:
        profile, version, _ = load_current_editorial_profile_in_transaction(
            session,
            owner_id=owner_id,
            profile_id=profile_id,
        )
        view = _availability(session, profile, version, now)
        if not view.selectable:
            raise ApplicationError("editorial_source_unavailable", context={"reason": view.reason})
