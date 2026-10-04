"""Current body admission, backed by the original component policy and operator audit."""

from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from connections.editorial_body_schemas import EditorialBodyApprovalInput, EditorialBodyApprovalView
from connections.editorial_rsshub import (
    load_current_editorial_profile_in_transaction,
    require_editorial_profile_ready_in_transaction,
)
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
from sources.editorial_body import EditorialBodyAdmission
from sources.editorial_schemas import EditorialSourceConfiguration, fingerprint


def editorial_body_component_policy(
    *, profile_id: UUID, configuration: EditorialSourceConfiguration
) -> ComponentPolicyInput:
    body = configuration.body_extraction
    if body is None or body.review is None or not body.enabled or not body.required:
        raise ApplicationError(
            "editorial_source_unavailable", context={"reason": "body_review_required"}
        )
    digest = fingerprint(configuration.model_dump(mode="json")).hex()
    review_digest = fingerprint(body.review.model_dump(mode="json")).hex()
    return ComponentPolicyInput(
        component_key=f"collector.editorial_body.{profile_id.hex}",
        component_version=f"editorial-body-v1:{digest}",
        upstream_revision=None,
        patched_revision=None,
        cost_class=CostClass.ZERO_PRICE,
        enabled_for_core=True,
        terms_reference=f"body-review:v1:{review_digest}",
        reviewed_at=body.review.reviewed_at,
    )


def approve_editorial_body_profile_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    profile_id: UUID,
    command: EditorialBodyApprovalInput,
    now: datetime,
) -> EditorialBodyApprovalView:
    profile, version, configuration = load_current_editorial_profile_in_transaction(
        session, owner_id=owner_id, profile_id=profile_id
    )
    accept_audit_in_transaction(
        session,
        owner_id=owner_id,
        operation_id=command.operation_id,
        action="editorial_source.body_approval",
        target_ref=f"editorial-source:{profile_id}",
        reason=command.reason,
        payload=command.model_dump(mode="json"),
        now=now,
        before_state={"revision": profile.revision, "configuration_version": version.version},
    )
    completed = load_completed_audit_in_transaction(
        session, owner_id=owner_id, operation_id=command.operation_id
    )
    if completed is not None:
        return EditorialBodyApprovalView.model_validate(completed)
    digest = fingerprint(configuration.model_dump(mode="json")).hex()
    if (
        profile.revision != command.expected_revision
        or version.version != command.configuration_version
        or digest != command.configuration_sha256
    ):
        raise ApplicationError("editorial_version_conflict")
    body = configuration.body_extraction
    if (
        body is None
        or body.review != command.review
        or not body.review.reviewed_at <= now < body.review.expires_at
    ):
        raise ApplicationError(
            "editorial_source_unavailable", context={"reason": "body_review_required"}
        )
    policy = ResourceBudgetService(session, clock=lambda: now).save_component_policy_in_transaction(
        owner_id=owner_id,
        command=editorial_body_component_policy(profile_id=profile_id, configuration=configuration),
    )
    result = EditorialBodyApprovalView(
        profile_id=profile_id,
        revision=profile.revision,
        configuration_version=version.version,
        configuration_sha256=digest,
        policy_version=policy.policy_version,
        reviewed_at=command.review.reviewed_at,
        expires_at=command.review.expires_at,
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


def require_editorial_body_execution_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    profile_id: UUID,
    configuration_version: int,
    revision: int,
    now: datetime,
) -> EditorialBodyAdmission:
    profile, version, configuration = load_current_editorial_profile_in_transaction(
        session, owner_id=owner_id, profile_id=profile_id
    )
    if profile.revision != revision or version.version != configuration_version:
        raise ApplicationError("editorial_version_conflict")
    require_editorial_profile_ready_in_transaction(
        session, profile=profile, version=version, now=now
    )
    command = editorial_body_component_policy(profile_id=profile_id, configuration=configuration)
    body = configuration.body_extraction
    assert body is not None and body.review is not None
    if not body.review.reviewed_at <= now < body.review.expires_at or not ResourceBudgetService(
        session, clock=lambda: now
    ).component_policy_matches_in_transaction(owner_id=owner_id, command=command):
        raise ApplicationError(
            "editorial_source_unavailable", context={"reason": "body_review_required"}
        )
    # The current policy must explicitly retain the body, rather than merely admit metadata.
    admitted = SourceAccessPolicyService(session, clock=lambda: now).admit_payload_in_transaction(
        owner_id=owner_id,
        source_key=profile.source_key,
        capability=SourceCapability.SEARCH,
        data_class=DataClass.STRUCTURED,
        collected_at=now,
        payload={
            "body": "body extraction permission check",
            "text_scope": "full",
            "text_origin": "machine_extracted",
            "text_origin_ref": "firecrawl/2.11.162",
            "title": "body extraction permission check",
            "canonical_url": "https://example.com/",
            "external_id": "body-permission-check",
        },
    )
    required = {
        "body",
        "text_scope",
        "text_origin",
        "text_origin_ref",
        "title",
        "canonical_url",
        "external_id",
    }
    if admitted.policy_version != version.policy_version or not required.issubset(admitted.fields):
        raise ApplicationError(
            "editorial_source_unavailable", context={"reason": "body_policy_required"}
        )
    return EditorialBodyAdmission(
        profile_id=profile_id,
        configuration_version=version.version,
        profile_revision=profile.revision,
        configuration_sha256=fingerprint(configuration.model_dump(mode="json")).hex(),
        proof_reference=command.terms_reference,
        component_version=command.component_version,
        reviewed_at=body.review.reviewed_at,
        expires_at=body.review.expires_at,
        allowed_hosts=frozenset(body.allowed_hosts),
        read_allowed=True,
        save_allowed=True,
        zero_supplier_fee_verified=True,
        target_egress_verified=True,
    )
