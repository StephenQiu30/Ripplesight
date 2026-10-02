"""Preview admission and result reads, using the original Job and operator audit."""

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from connections.editorial_preview import (
    load_editorial_preview_profile_in_transaction,
    preview_profile_hash,
)
from connections.editorial_services import capability_for
from core.config import Settings
from core.errors import ApplicationError
from jobs.editorial_preview import (
    load_editorial_preview_job_state_in_transaction,
    recover_editorial_preview_budgets_in_transaction,
    require_no_unresolved_editorial_preview_in_transaction,
)
from jobs.schemas import JobAcceptanceInput, JobObservationContext, JobView
from jobs.services import (
    JobService,
    load_job_execution_configuration,
    load_job_execution_configuration_by_operation,
)
from operations.services import (
    accept_audit_in_transaction,
    complete_audit_in_transaction,
    load_completed_audit_in_transaction,
)
from sources.editorial_preview_rules import preview_sample
from sources.editorial_preview_schemas import (
    EditorialPreviewJobView,
    EditorialPreviewReviewInput,
    EditorialPreviewReviewView,
    EditorialRemotePreviewInput,
    EditorialSamplePreviewInput,
    EditorialSourcePreviewView,
)
from sources.editorial_schemas import fingerprint


class EditorialSourcePreviewService:
    def __init__(
        self, session: Session, settings: Settings, *, clock: Callable[[], datetime] | None = None
    ):
        self.session, self.settings = session, settings
        self.clock = clock or (lambda: datetime.now(UTC))

    def preview_sample(
        self, *, owner_id: UUID, command: EditorialSamplePreviewInput
    ) -> EditorialSourcePreviewView:
        # Given sample data is interpreted locally; it is not a source request or stored article.
        self.session.rollback()
        with self.session.begin():
            _audit, replayed = accept_audit_in_transaction(
                self.session,
                owner_id=owner_id,
                operation_id=command.operation_id,
                action="editorial.source.preview.sample",
                target_ref="source:draft",
                reason=command.reason,
                now=self.clock(),
                payload={
                    **command.model_dump(mode="json"),
                    "sample_sha256": fingerprint(command.sample).hex(),
                },
                before_state={"sample_sha256": fingerprint(command.sample).hex()},
            )
            if replayed:
                saved = load_completed_audit_in_transaction(
                    self.session, owner_id=owner_id, operation_id=command.operation_id
                )
                if saved is not None:
                    return EditorialSourcePreviewView.model_validate(saved)
            try:
                result = preview_sample(command, now=self.clock())
            except (ValueError, UnicodeError, KeyError, IndexError):
                raise ApplicationError("invalid_editorial_input") from None
            complete_audit_in_transaction(
                self.session,
                owner_id=owner_id,
                operation_id=command.operation_id,
                now=self.clock(),
                after_state=result.model_dump(mode="json"),
            )
            return result

    def enqueue(
        self, *, owner_id: UUID, profile_id: UUID, command: EditorialRemotePreviewInput
    ) -> JobView:
        self.session.rollback()
        with self.session.begin():
            profile = load_editorial_preview_profile_in_transaction(
                self.session,
                owner_id=owner_id,
                profile_id=profile_id,
                expected_revision=command.expected_revision,
                now=self.clock(),
            )
            require_no_unresolved_editorial_preview_in_transaction(
                self.session,
                owner_id=owner_id,
                profile_id=profile_id,
                operation_id=command.operation_id,
            )
            _audit, _replayed = accept_audit_in_transaction(
                self.session,
                owner_id=owner_id,
                operation_id=command.operation_id,
                action="editorial.source.preview",
                target_ref=f"source:{profile_id}",
                reason=command.reason,
                payload={"profile_id": str(profile_id), **command.model_dump(mode="json")},
                now=self.clock(),
            )
            existing = load_job_execution_configuration_by_operation(
                self.session,
                owner_id=owner_id,
                kind="source.editorial.preview",
                operation_id=command.operation_id,
            )
            if existing is not None:
                profile_hash = existing.scope.get("preview_profile_sha256")
                if profile_hash != preview_profile_hash(profile):
                    raise ApplicationError("editorial_version_conflict")
            return JobService(self.session, clock=self.clock).accept_in_transaction(
                owner_id=owner_id,
                command=JobAcceptanceInput(
                    operation_id=command.operation_id,
                    kind="source.editorial.preview",
                    observation=JobObservationContext(
                        configuration_ref=f"editorial-source:{profile_id}",
                        configuration_version=profile.configuration_version,
                        source_key=profile.source_key,
                        source_capability=capability_for(profile.configuration.kind),
                    ),
                    scope={
                        "profile_id": str(profile_id),
                        "revision": profile.revision,
                        "preview_profile_sha256": preview_profile_hash(profile),
                        "preview_kind": profile.configuration.kind,
                    },
                ),
            )

    def read(self, *, owner_id: UUID, job_id: UUID) -> EditorialPreviewJobView:
        self.session.rollback()
        with self.session.begin():
            config = load_job_execution_configuration(self.session, job_id=job_id)
            if (
                config is None
                or config.owner_id != owner_id
                or config.kind != "source.editorial.preview"
            ):
                raise ApplicationError("resource_not_found")
            profile = load_editorial_preview_profile_in_transaction(
                self.session,
                owner_id=owner_id,
                profile_id=UUID(str(config.scope["profile_id"])),
                expected_revision=int(str(config.scope["revision"])),
                now=self.clock(),
            )
            if preview_profile_hash(profile) != config.scope.get("preview_profile_sha256"):
                raise ApplicationError("editorial_version_conflict")
            saved = load_completed_audit_in_transaction(
                self.session, owner_id=owner_id, operation_id=config.operation_id
            )
            preview = EditorialSourcePreviewView.model_validate(saved) if saved else None
            state = load_editorial_preview_job_state_in_transaction(
                self.session, owner_id=owner_id, job_id=job_id, operation_id=config.operation_id
            )
            if preview is None and state.started and state.terminal:
                preview = EditorialSourcePreviewView.model_validate(
                    dict(
                        mode="remote",
                        status="unknown",
                        kind=config.scope.get("preview_kind"),
                        count=0,
                        ms=0,
                        requests=state.requests,
                        items=(),
                        reason="source_preview_outcome_unknown",
                    )
                )
            if preview is not None and (preview.items or preview.status == "complete"):
                load_editorial_preview_profile_in_transaction(
                    self.session,
                    owner_id=owner_id,
                    profile_id=profile.id,
                    expected_revision=profile.revision,
                    now=self.clock(),
                    require_remote=True,
                )
        job = JobService(self.session, clock=self.clock).get_status(
            owner_id=owner_id, job_id=job_id
        )
        return EditorialPreviewJobView(job=job, preview=preview)

    def review(
        self, *, owner_id: UUID, job_id: UUID, command: EditorialPreviewReviewInput
    ) -> EditorialPreviewReviewView:
        """Acknowledge the exact unknown original operation; preserve all original receipts."""
        self.session.rollback()
        with self.session.begin():
            config = load_job_execution_configuration(self.session, job_id=job_id)
            if (
                config is None
                or config.owner_id != owner_id
                or config.kind != "source.editorial.preview"
            ):
                raise ApplicationError("resource_not_found")
            if config.operation_id != command.preview_operation_id:
                raise ApplicationError("editorial_version_conflict")
            _, replayed = accept_audit_in_transaction(
                self.session,
                owner_id=owner_id,
                operation_id=command.operation_id,
                action="editorial.source.preview.review",
                target_ref=str(job_id),
                reason=command.reason,
                payload=command.model_dump(mode="json"),
                now=self.clock(),
            )
            if replayed:
                saved = load_completed_audit_in_transaction(
                    self.session,
                    owner_id=owner_id,
                    operation_id=command.operation_id,
                )
                if saved is not None:
                    return EditorialPreviewReviewView.model_validate(saved)
            profile = load_editorial_preview_profile_in_transaction(
                self.session,
                owner_id=owner_id,
                profile_id=UUID(str(config.scope["profile_id"])),
                expected_revision=command.expected_revision,
                now=self.clock(),
            )
            original = load_completed_audit_in_transaction(
                self.session,
                owner_id=owner_id,
                operation_id=config.operation_id,
            )
            state = load_editorial_preview_job_state_in_transaction(
                self.session, owner_id=owner_id, job_id=job_id, operation_id=config.operation_id
            )
            if not state.terminal:
                raise ApplicationError("editorial_version_conflict")
            if original is None and state.started:
                unknown = EditorialSourcePreviewView.model_validate(
                    dict(
                        mode="remote",
                        status="unknown",
                        kind=config.scope["preview_kind"],
                        count=0,
                        ms=0,
                        requests=state.requests,
                        items=(),
                        reason="source_preview_outcome_unknown",
                    )
                )
                recover_editorial_preview_budgets_in_transaction(
                    self.session,
                    owner_id=owner_id,
                    job_id=job_id,
                    operation_id=config.operation_id,
                    now=self.clock(),
                )
                original = unknown.model_dump(mode="json")
                complete_audit_in_transaction(
                    self.session,
                    owner_id=owner_id,
                    operation_id=config.operation_id,
                    after_state=original,
                    now=self.clock(),
                )
            if (
                original is None
                or EditorialSourcePreviewView.model_validate(original).status != "unknown"
            ):
                raise ApplicationError("editorial_version_conflict")
            result = EditorialPreviewReviewView(
                job_id=job_id,
                profile_id=profile.id,
                preview_operation_id=config.operation_id,
                review_operation_id=command.operation_id,
                revision=profile.revision,
            )
            complete_audit_in_transaction(
                self.session,
                owner_id=owner_id,
                operation_id=command.operation_id,
                after_state=result.model_dump(mode="json"),
                now=self.clock(),
            )
            return result
