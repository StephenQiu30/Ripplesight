"""Explicit test-only approvals; transport setup never supplies platform permission."""

from uuid import UUID

from connections.presets import SourcePreset
from connections.schemas import SourcePresetApplyView
from connections.services import SourcePresetService
from evidence.schemas import (
    AccessBasis,
    AccessPolicyStatus,
    DataClass,
    RetentionPolicyInput,
    SourceAccessPolicyInput,
)
from evidence.services import RetentionPolicyService, SourceAccessPolicyService
from jobs.schemas import BudgetPolicyInput, ComponentPolicyInput
from jobs.services import ResourceBudgetService
from sources.contracts import SourceCapability


class ControlledHotlistPresetService(SourcePresetService):
    """Prepare a fully approved controlled source before configuring its transport."""

    def apply_in_transaction(
        self, *, owner_id: UUID, preset: SourcePreset
    ) -> SourcePresetApplyView:
        if any(item.capability is SourceCapability.HOTLIST for item in preset.capabilities):
            now = self._clock()
            for item in preset.capabilities:
                access = SourceAccessPolicyService(
                    self._session, clock=self._clock
                ).save_in_transaction(
                    owner_id=owner_id,
                    command=SourceAccessPolicyInput(
                        source_key=preset.source_key,
                        capability=item.capability,
                        status=AccessPolicyStatus.APPROVED,
                        enabled=True,
                        access_basis=AccessBasis.WRITTEN_PERMISSION,
                        terms_reference="https://example.com/controlled-hotlist-collection",
                        processing_purpose=item.processing_purpose,
                        component_name=preset.component_name,
                        component_version=preset.component_version,
                        component_license=preset.component_license,
                        field_purposes=dict(item.field_purposes),
                        reviewed_at=now,
                    ),
                )
                RetentionPolicyService(self._session, clock=self._clock).save_in_transaction(
                    owner_id=owner_id,
                    command=RetentionPolicyInput(
                        source_policy_id=access.id,
                        data_class=DataClass.STRUCTURED,
                        requested_days=90,
                        source_max_days=90,
                    ),
                )
            resources = ResourceBudgetService(self._session, clock=self._clock)
            resources.save_component_policy_in_transaction(
                owner_id=owner_id,
                command=ComponentPolicyInput(
                    component_key=preset.component_name,
                    component_version=preset.component_version,
                    upstream_revision=preset.upstream_revision,
                    patched_revision=preset.patched_revision,
                    cost_class=preset.component_cost_class,
                    enabled_for_core=True,
                    terms_reference=preset.component_terms_reference,
                    reviewed_at=now,
                ),
            )
            resources.save_budget_policy_in_transaction(
                owner_id=owner_id,
                command=BudgetPolicyInput(
                    budget_key=preset.budget.budget_key,
                    metric=preset.budget.metric,
                    scope_kind=preset.budget.scope_kind,
                    scope_reference=preset.budget.scope_reference,
                    limit_units=preset.budget.limit_units,
                    window_seconds=preset.budget.window_seconds,
                    window_anchor_at=preset.budget.window_anchor_at,
                    enabled=True,
                ),
            )
        return super().apply_in_transaction(owner_id=owner_id, preset=preset)
