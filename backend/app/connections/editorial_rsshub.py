"""Server-side RSSHub route approvals in the original component policy and audit.

No HTTP, new queue, policy upgrade or transaction rollback occurs in these helpers.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from connections.editorial_models import EditorialSourceProfile, EditorialSourceVersion
from connections.editorial_schemas import EditorialRsshubApprovalInput, EditorialRsshubApprovalView
from connections.models import SourceConnection, SourceConnectionVersion
from connections.schemas import SourceExecutionPolicy
from core.errors import ApplicationError
from evidence.schemas import DataClass
from evidence.services import SourceAccessPolicyService
from jobs.schemas import ComponentPolicyInput, CostClass
from jobs.services import ResourceBudgetService
from operations.services import (
    accept_audit_in_transaction,
    complete_audit_in_transaction,
    load_completed_audit_in_transaction,
)
from sources.contracts import SourceCapability
from sources.editorial_rsshub import EditorialRsshubAdmission, rsshub_route_blocker
from sources.editorial_schemas import EditorialSourceConfiguration, fingerprint


def _unavailable(reason: str) -> ApplicationError:
    return ApplicationError("editorial_source_unavailable", context={"reason": reason})


def load_current_editorial_profile_in_transaction(
    session: Session, *, owner_id: UUID, profile_id: UUID
) -> tuple[EditorialSourceProfile, EditorialSourceVersion, EditorialSourceConfiguration]:
    if not session.in_transaction():
        raise RuntimeError("editorial admission requires caller transaction")
    profile = session.scalar(
        select(EditorialSourceProfile)
        .where(EditorialSourceProfile.owner_id == owner_id, EditorialSourceProfile.id == profile_id)
        .with_for_update()
    )
    if profile is None:
        raise ApplicationError("resource_not_found")
    version = session.get(EditorialSourceVersion, (profile.id, profile.current_version))
    if version is None or version.owner_id != owner_id:
        raise ApplicationError("resource_not_found")
    return profile, version, EditorialSourceConfiguration.model_validate(version.configuration)


def require_editorial_profile_ready_in_transaction(
    session: Session,
    *,
    profile: EditorialSourceProfile,
    version: EditorialSourceVersion,
    now: datetime,
) -> None:
    if not session.in_transaction() or now.utcoffset() is None:
        raise RuntimeError("editorial admission requires a caller transaction and aware time")
    if not profile.enabled:
        raise ApplicationError("editorial_source_disabled")
    connection = session.scalar(
        select(SourceConnection)
        .where(
            SourceConnection.owner_id == profile.owner_id,
            SourceConnection.id == version.connection_id,
        )
        .with_for_update()
    )
    connection_version = session.get(
        SourceConnectionVersion, (version.connection_id, version.connection_version)
    )
    if (
        connection is None
        or connection_version is None
        or connection_version.owner_id != profile.owner_id
        or connection.status != "active"
    ):
        raise ApplicationError("connection_disabled")
    if connection.current_version != version.connection_version:
        raise ApplicationError("connection_version_conflict")
    capability = (
        SourceCapability.AUTHOR_POSTS if version.kind == "mp_account" else SourceCapability.SEARCH
    )
    policy = SourceAccessPolicyService(session, clock=lambda: now)
    policy.require_admission_ready_in_transaction(
        owner_id=profile.owner_id,
        source_key=profile.source_key,
        capability=capability,
        data_class=DataClass.STRUCTURED,
    )
    admitted = policy.admit_payload_in_transaction(
        owner_id=profile.owner_id,
        source_key=profile.source_key,
        capability=capability,
        data_class=DataClass.STRUCTURED,
        collected_at=now,
        payload={"title": profile.name},
    )
    if admitted.policy_version != version.policy_version:
        raise ApplicationError("editorial_version_conflict")


def rsshub_component_policy(
    *, profile_id: UUID, configuration: EditorialSourceConfiguration
) -> ComponentPolicyInput:
    rsshub = configuration.rsshub
    if rsshub is None:
        raise _unavailable("rsshub_mode_required")
    digest = fingerprint(configuration.model_dump(mode="json")).hex()
    return ComponentPolicyInput(
        component_key=f"collector.rsshub.{profile_id.hex}",
        component_version=f"editorial-rsshub-v1:{digest}",
        upstream_revision=rsshub.revision,
        patched_revision=rsshub.revision,
        cost_class=CostClass.ZERO_PRICE,
        enabled_for_core=True,
        # The full declaration and all six evidence refs are retained in the
        # operator audit, and their exact hash binds this original policy row.
        terms_reference=f"rsshub-route-review:v1:sha256:{digest}",
        reviewed_at=rsshub.review.reviewed_at,
    )


def rsshub_execution_policy(configuration: EditorialSourceConfiguration) -> SourceExecutionPolicy:
    rsshub = configuration.rsshub
    if rsshub is None:
        raise ValueError("RSSHub execution policy requires a frozen RSSHub configuration")
    return SourceExecutionPolicy(
        min_interval_seconds=rsshub.min_interval_minutes * 60,
        quiet_windows=(),
        max_queries=1,
        max_items_per_query=rsshub.max_items,
        max_requests=rsshub.max_local_requests,
        max_seconds=rsshub.max_seconds,
        hard_timeout_seconds=rsshub.max_seconds,
        max_concurrency=1,
        enabled=True,
    )


def _require_frozen_connection(
    session: Session,
    profile: EditorialSourceProfile,
    version: EditorialSourceVersion,
    configuration: EditorialSourceConfiguration,
) -> None:
    connection = session.get(SourceConnection, version.connection_id)
    frozen = session.get(
        SourceConnectionVersion, (version.connection_id, version.connection_version)
    )
    if (
        connection is None
        or connection.owner_id != profile.owner_id
        or connection.source_key != profile.source_key
        or connection.current_version != version.connection_version
        or frozen is None
        or frozen.owner_id != profile.owner_id
        or frozen.auth_kind != "none"
        or frozen.secret_ref is not None
        or frozen.config != {"allowed_hosts": list(configuration.allowed_hosts)}
        or frozen.execution_policy != rsshub_execution_policy(configuration).model_dump(mode="json")
    ):
        raise _unavailable("rsshub_connection_contract_mismatch")


def approve_editorial_rsshub_profile_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    profile_id: UUID,
    command: EditorialRsshubApprovalInput,
    now: datetime,
) -> EditorialRsshubApprovalView:
    profile, version, configuration = load_current_editorial_profile_in_transaction(
        session, owner_id=owner_id, profile_id=profile_id
    )
    if now.utcoffset() is None:
        raise ValueError("RSSHub approval time must be aware")
    payload = command.model_dump(mode="json")
    accept_audit_in_transaction(
        session,
        owner_id=owner_id,
        operation_id=command.operation_id,
        action="editorial_source.rsshub_approval",
        target_ref=f"editorial-source:{profile_id}",
        reason=command.reason,
        payload=payload,
        now=now,
        before_state={"revision": profile.revision, "configuration_version": version.version},
    )
    completed = load_completed_audit_in_transaction(
        session, owner_id=owner_id, operation_id=command.operation_id
    )
    if completed is not None:
        return EditorialRsshubApprovalView.model_validate(completed)
    digest = fingerprint(configuration.model_dump(mode="json")).hex()
    if (
        profile.revision != command.expected_revision
        or version.version != command.configuration_version
        or digest != command.configuration_sha256
    ):
        raise ApplicationError("editorial_version_conflict")
    rsshub = configuration.rsshub
    if rsshub is None or rsshub.review != command.review:
        raise _unavailable("rsshub_review_mismatch")
    blocker = rsshub_route_blocker(rsshub)
    if blocker:
        raise _unavailable(blocker)
    if not rsshub.review.reviewed_at <= now < rsshub.review.expires_at:
        raise _unavailable("rsshub_review_expired")
    if version.interval_minutes < rsshub.min_interval_minutes:
        raise _unavailable("rsshub_interval_unapproved")
    _require_frozen_connection(session, profile, version, configuration)
    policy = ResourceBudgetService(session, clock=lambda: now).save_component_policy_in_transaction(
        owner_id=owner_id,
        command=rsshub_component_policy(profile_id=profile_id, configuration=configuration),
    )
    result = EditorialRsshubApprovalView(
        profile_id=profile_id,
        revision=profile.revision,
        configuration_version=version.version,
        configuration_sha256=digest,
        policy_version=policy.policy_version,
        reviewed_at=rsshub.review.reviewed_at,
        expires_at=rsshub.review.expires_at,
        enabled=profile.enabled,
    )
    complete_audit_in_transaction(
        session,
        owner_id=owner_id,
        operation_id=command.operation_id,
        after_state=result.model_dump(mode="json"),
        now=now,
    )
    return result


def require_editorial_rsshub_execution_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    profile_id: UUID,
    configuration_version: int,
    revision: int,
    now: datetime,
) -> EditorialRsshubAdmission:
    profile, version, configuration = load_current_editorial_profile_in_transaction(
        session, owner_id=owner_id, profile_id=profile_id
    )
    if profile.revision != revision or version.version != configuration_version:
        raise ApplicationError("editorial_version_conflict")
    require_editorial_profile_ready_in_transaction(
        session, profile=profile, version=version, now=now
    )
    rsshub = configuration.rsshub
    if rsshub is None:
        raise _unavailable("rsshub_mode_required")
    blocker = rsshub_route_blocker(rsshub)
    if blocker:
        raise _unavailable(blocker)
    if not rsshub.review.reviewed_at <= now < rsshub.review.expires_at:
        raise _unavailable("rsshub_review_expired")
    if version.interval_minutes < rsshub.min_interval_minutes:
        raise _unavailable("rsshub_interval_unapproved")
    _require_frozen_connection(session, profile, version, configuration)
    if not ResourceBudgetService(
        session, clock=lambda: now
    ).component_policy_matches_in_transaction(
        owner_id=owner_id,
        command=rsshub_component_policy(profile_id=profile_id, configuration=configuration),
    ):
        raise _unavailable("rsshub_route_review_required")
    return EditorialRsshubAdmission(
        configuration_sha256=fingerprint(configuration.model_dump(mode="json")).hex(),
        revision=rsshub.revision,
        reviewed_at=rsshub.review.reviewed_at,
        expires_at=rsshub.review.expires_at,
        max_downstream_requests=rsshub.max_downstream_requests,
    )
