"""Call-local current source admissions for bounded bulk permission rechecks."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from evidence.models import RetentionPolicy, SourceAccessPolicy
from evidence.schemas import AdmittedSourcePayload, DataClass
from evidence.services import minimize_payload
from sources.contracts import SourceCapability


@dataclass(frozen=True, slots=True)
class CurrentSourceAdmission:
    owner_id: UUID
    source_key: str
    capability: SourceCapability
    policy_id: UUID
    policy_version: int
    field_purposes: dict[str, str]
    retention_policy_id: UUID
    retention_policy_version: int
    effective_days: int
    data_class: DataClass

    def admit(
        self, *, collected_at: datetime, payload: Mapping[str, object], now: datetime
    ) -> AdmittedSourcePayload:
        if collected_at.utcoffset() is None or collected_at > now:
            raise ValueError("collected_at requires aware past time")
        fields = minimize_payload(field_purposes=self.field_purposes, payload=payload)
        if not fields:
            raise ValueError("payload contains no admitted fields")
        return AdmittedSourcePayload(
            policy_id=self.policy_id,
            policy_version=self.policy_version,
            owner_id=self.owner_id,
            source_key=self.source_key,
            capability=self.capability,
            retention_policy_id=self.retention_policy_id,
            retention_policy_version=self.retention_policy_version,
            data_class=self.data_class,
            collected_at=collected_at,
            expires_at=collected_at + timedelta(days=self.effective_days),
            fields=fields,
        )


def load_current_source_admissions_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    source_contexts: set[tuple[str, SourceCapability]],
    data_class: DataClass,
    now: datetime,
) -> dict[tuple[str, SourceCapability], CurrentSourceAdmission]:
    if not session.in_transaction() or now.utcoffset() is None or len(source_contexts) > 1000:
        raise ValueError("current admissions require aware bounded caller transaction")
    if not source_contexts:
        return {}
    rows = session.execute(
        select(SourceAccessPolicy, RetentionPolicy)
        .join(
            RetentionPolicy,
            (RetentionPolicy.owner_id == SourceAccessPolicy.owner_id)
            & (RetentionPolicy.source_policy_id == SourceAccessPolicy.id),
        )
        .where(
            SourceAccessPolicy.owner_id == owner_id,
            tuple_(SourceAccessPolicy.source_key, SourceAccessPolicy.capability).in_(
                {(key, capability.value) for key, capability in source_contexts}
            ),
            RetentionPolicy.data_class == data_class.value,
        )
        .execution_options(populate_existing=True)
    ).all()
    result = {}
    for policy, retention in rows:
        if (
            policy.status != "approved"
            or not policy.enabled
            or not policy.field_purposes
            or (policy.review_expires_at is not None and policy.review_expires_at <= now)
            or retention.source_policy_version != policy.policy_version
            or retention.effective_days == 0
        ):
            continue
        capability = SourceCapability(policy.capability)
        result[policy.source_key, capability] = CurrentSourceAdmission(
            owner_id,
            policy.source_key,
            capability,
            policy.id,
            policy.policy_version,
            dict(policy.field_purposes),
            retention.id,
            retention.policy_version,
            retention.effective_days,
            data_class,
        )
    return result
