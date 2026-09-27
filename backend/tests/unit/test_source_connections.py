from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from connections.schemas import (
    ConnectionEvidenceKind,
    ConnectionEvidenceOutcome,
    PersistedReadEvidenceInput,
    ProbeEvidenceInput,
    SourceCapabilityStatus,
    SourceConnectionStatus,
    SourceCurrentVersionView,
    SourceEntryPoint,
    SourcePlatformStatus,
)
from connections.services import (
    CapabilityStatusFacts,
    aggregate_platform_status,
    list_current_source_connection_versions_in_transaction,
    resolve_capability_status,
)
from sources.contracts import SourceCapability, SourceStopReason


def test_current_connection_versions_include_disabled_sources_for_owner() -> None:
    owner_id = UUID(int=1)
    session = MagicMock(spec=Session)
    session.in_transaction.return_value = True
    session.execute.return_value.all.return_value = [
        ("disabled_source", 3),
        ("enabled_source", 1),
    ]

    result = list_current_source_connection_versions_in_transaction(session, owner_id=owner_id)

    assert result == (
        SourceCurrentVersionView(source_key="disabled_source", current_version=3),
        SourceCurrentVersionView(source_key="enabled_source", current_version=1),
    )
    session.execute.assert_called_once()
    statement = session.execute.call_args.args[0]
    assert owner_id in statement.compile().params.values()
    assert "source_connections.status" not in str(statement)


def test_current_connection_versions_require_transaction() -> None:
    session = MagicMock(spec=Session)
    session.in_transaction.return_value = False

    with pytest.raises(RuntimeError, match="caller's transaction"):
        list_current_source_connection_versions_in_transaction(session, owner_id=UUID(int=1))
    session.execute.assert_not_called()


@pytest.mark.parametrize(
    ("facts", "expected"),
    [
        (
            CapabilityStatusFacts(product_restricted=True),
            SourceCapabilityStatus.RESTRICTED,
        ),
        (CapabilityStatusFacts(), SourceCapabilityStatus.UNCONFIGURED),
        (
            CapabilityStatusFacts(connection_status=SourceConnectionStatus.DISABLED),
            SourceCapabilityStatus.DISABLED,
        ),
        (
            CapabilityStatusFacts(
                connection_status=SourceConnectionStatus.ACTIVE,
                policy_ready=False,
            ),
            SourceCapabilityStatus.RESTRICTED,
        ),
        (
            CapabilityStatusFacts(
                connection_status=SourceConnectionStatus.ACTIVE,
                policy_ready=True,
                evidence_kind=ConnectionEvidenceKind.PROBE,
                evidence_outcome=ConnectionEvidenceOutcome.SUCCEEDED,
            ),
            SourceCapabilityStatus.PENDING_VERIFICATION,
        ),
        (
            CapabilityStatusFacts(
                connection_status=SourceConnectionStatus.ACTIVE,
                policy_ready=True,
                evidence_kind=ConnectionEvidenceKind.PERSISTED_READ,
                evidence_outcome=ConnectionEvidenceOutcome.SUCCEEDED,
            ),
            SourceCapabilityStatus.AVAILABLE,
        ),
        (
            CapabilityStatusFacts(
                connection_status=SourceConnectionStatus.ACTIVE,
                policy_ready=True,
                evidence_kind=ConnectionEvidenceKind.PERSISTED_READ,
                evidence_outcome=ConnectionEvidenceOutcome.FAILED,
                stop_reason=SourceStopReason.AUTHENTICATION_REQUIRED,
            ),
            SourceCapabilityStatus.AUTHENTICATION_REQUIRED,
        ),
        (
            CapabilityStatusFacts(
                connection_status=SourceConnectionStatus.ACTIVE,
                policy_ready=True,
                evidence_kind=ConnectionEvidenceKind.PERSISTED_READ,
                evidence_outcome=ConnectionEvidenceOutcome.FAILED,
                stop_reason=SourceStopReason.ACCESS_DENIED,
            ),
            SourceCapabilityStatus.RESTRICTED,
        ),
    ],
)
def test_capability_status_uses_frozen_priority(
    facts: CapabilityStatusFacts,
    expected: SourceCapabilityStatus,
) -> None:
    assert resolve_capability_status(facts) is expected


def test_transient_failure_stays_pending_without_expiring_old_success_timestamp() -> None:
    last_success = datetime(2026, 9, 22, 8, tzinfo=UTC)
    facts = CapabilityStatusFacts(
        connection_status=SourceConnectionStatus.ACTIVE,
        policy_ready=True,
        evidence_kind=ConnectionEvidenceKind.PERSISTED_READ,
        evidence_outcome=ConnectionEvidenceOutcome.FAILED,
        stop_reason=SourceStopReason.UPSTREAM_ERROR,
        last_persisted_success_at=last_success,
    )

    assert resolve_capability_status(facts) is SourceCapabilityStatus.PENDING_VERIFICATION
    assert facts.last_persisted_success_at == last_success


def test_partial_is_only_a_platform_aggregate() -> None:
    assert (
        aggregate_platform_status(
            [
                SourceCapabilityStatus.AVAILABLE,
                SourceCapabilityStatus.RESTRICTED,
            ]
        )
        is SourcePlatformStatus.PARTIAL
    )
    assert (
        aggregate_platform_status([SourceCapabilityStatus.UNCONFIGURED] * 8)
        is SourcePlatformStatus.UNCONFIGURED
    )


def test_failed_probe_requires_a_stable_reason() -> None:
    with pytest.raises(ValidationError, match="stop_reason"):
        ProbeEvidenceInput(
            operation_id=UUID(int=1),
            connection_id=UUID(int=2),
            connection_version=1,
            capability=SourceCapability.SEARCH,
            entry_point=SourceEntryPoint.MANUAL,
            outcome=ConnectionEvidenceOutcome.FAILED,
            stop_reason=None,
            component_name="controlled-probe",
            component_version="1",
        )


def test_successful_persisted_read_requires_a_resource_reference() -> None:
    with pytest.raises(ValidationError, match="resource_ref"):
        PersistedReadEvidenceInput(
            operation_id=UUID(int=1),
            connection_id=UUID(int=2),
            connection_version=1,
            capability=SourceCapability.SEARCH,
            entry_point=SourceEntryPoint.MANUAL,
            outcome=ConnectionEvidenceOutcome.SUCCEEDED,
            stop_reason=None,
            resource_ref=None,
            component_name="controlled-collector",
            component_version="1",
        )


@pytest.mark.parametrize("version", [None, 0, -1])
@pytest.mark.parametrize("schema", [ProbeEvidenceInput, PersistedReadEvidenceInput])
def test_evidence_requires_explicit_positive_connection_version(schema, version) -> None:
    payload = {
        "operation_id": UUID(int=1),
        "connection_id": UUID(int=2),
        "capability": "search",
        "entry_point": "manual",
        "outcome": "failed",
        "stop_reason": "authentication_required",
        "component_name": "controlled-probe",
        "component_version": "1",
    }
    if version is not None:
        payload["connection_version"] = version
    with pytest.raises(ValidationError, match="connection_version"):
        schema.model_validate(payload)
