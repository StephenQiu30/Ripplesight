"""Editable source configuration, bounded page staging, and atomic content checkpoints.

This domain owns source configuration/checkpoints. Content/Evidence/Job operations use
services and DTOs in the same outer transaction; no foreign business ORM is imported.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hmac import compare_digest
from hmac import new as hmac_new
from ipaddress import ip_address
from typing import Literal, cast
from uuid import UUID, uuid4, uuid5

from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from analysis.editorial_schemas import EditorialSourceInput, SourceKind, Tier
from analysis.editorial_services import EditorialService
from connections.editorial_body_admission import (
    approve_editorial_body_profile_in_transaction,
    require_editorial_body_execution_in_transaction,
)
from connections.editorial_body_schemas import EditorialBodyApprovalInput, EditorialBodyApprovalView
from connections.editorial_models import (
    EditorialSourceMaterialReceipt,
    EditorialSourceProfile,
    EditorialSourceRun,
    EditorialSourceVersion,
)
from connections.editorial_rsshub import (
    approve_editorial_rsshub_profile_in_transaction,
    require_editorial_rsshub_execution_in_transaction,
    rsshub_execution_policy,
)
from connections.editorial_schemas import (
    EditorialGroupBacklogReviewInput,
    EditorialGroupBacklogReviewResult,
    EditorialGroupBacklogView,
    EditorialPollInput,
    EditorialProfileInput,
    EditorialRsshubApprovalInput,
    EditorialRsshubApprovalView,
    EditorialRunReviewInput,
    EditorialSourceOperationalHealth,
    ExternalEditorialInput,
    ExternalIngressItem,
    ExternalIngressReceipt,
)
from connections.editorial_target_dedup import require_unique_rsshub_target_in_transaction
from connections.models import SourceConnection, SourceConnectionVersion
from content.editorial_body import (
    complete_editorial_body_in_transaction,
    load_editorial_body_target_in_transaction,
    require_editorial_body_input_in_transaction,
)
from content.editorial_ingest import EditorialContentIngestService
from content.editorial_schemas import EditorialContentInput, EditorialContentResult
from core.errors import ApplicationError
from events.heat import record_source_fetch_success_in_transaction
from evidence.schemas import DataClass
from evidence.services import (
    RetentionPolicyUnavailableError,
    SourceAccessPolicyService,
    SourceAccessUnavailableError,
)
from jobs.editorial_member import (
    load_content_job_context_for_editorial_member_in_transaction,
    load_editorial_group_manifest_in_transaction,
)
from jobs.external_ingress import (
    load_external_ingress_job_in_transaction,
    require_external_ingress_rate_in_transaction,
)
from jobs.schemas import JobAcceptanceInput, JobObservationContext, JobStatus, JobView
from jobs.services import (
    JobService,
    load_content_job_context,
    load_job_cancellation_state_in_transaction,
    load_job_execution_configuration,
)
from operations.services import (
    accept_audit_in_transaction,
    complete_audit_in_transaction,
    load_completed_audit_in_transaction,
)
from sources.contracts import SourceCapability, WebPageResult
from sources.editorial_identity import verify_editorial_native_identity
from sources.editorial_registry import EditorialKnownMaterial
from sources.editorial_schemas import (
    EditorialBodyCheckpoint,
    EditorialBodyTarget,
    EditorialCursor,
    EditorialDue,
    EditorialMaterial,
    EditorialPage,
    EditorialProfileView,
    EditorialRunResult,
    EditorialSourceConfiguration,
    fingerprint,
)

type Clock = Callable[[], datetime]
type Guard = Callable[[Session, UUID, UUID], bool]
type Sink = Callable[[Session, UUID, EditorialContentInput], EditorialContentResult]


def require_official_x_connection_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    connection_id: UUID,
    connection_version: int,
    now: datetime,
) -> None:
    if not session.in_transaction():
        raise RuntimeError("official X admission requires caller transaction")
    connection = session.scalar(
        select(SourceConnection)
        .where(
            SourceConnection.owner_id == owner_id,
            SourceConnection.id == connection_id,
        )
        .with_for_update()
    )
    version = session.get(SourceConnectionVersion, (connection_id, connection_version))
    if (
        connection is None
        or version is None
        or version.owner_id != owner_id
        or connection.source_key != "x"
        or connection.status != "active"
        or version.auth_kind != "server_credential"
    ):
        raise ApplicationError("connection_disabled")
    if connection.current_version != connection_version:
        raise ApplicationError("connection_version_conflict")
    policy = SourceAccessPolicyService(session, clock=lambda: now)
    policy.require_admission_ready_in_transaction(
        owner_id=owner_id,
        source_key="x",
        capability=SourceCapability.SEARCH,
        data_class=DataClass.STRUCTURED,
    )
    admitted = policy.admit_payload_in_transaction(
        owner_id=owner_id,
        source_key="x",
        capability=SourceCapability.SEARCH,
        data_class=DataClass.STRUCTURED,
        collected_at=now,
        payload={"external_id": "0", "body": "admission-field-check", "text_scope": "full"},
    )
    if not {"external_id", "body", "text_scope"}.issubset(admitted.fields):
        raise ApplicationError("codex_source_unavailable")


@dataclass(frozen=True)
class PreparedEditorialRun:
    result: EditorialRunResult
    profile: EditorialProfileView
    cursor: EditorialCursor
    known: Mapping[str, EditorialKnownMaterial]
    prepared_page: EditorialPage | None
    should_collect: bool
    source_added_at: datetime | None = None


@dataclass
class KnownMaterial:
    body_status: str
    body_retry_count: int
    published_at: datetime | None
    created_at: datetime
    detail_title: str | None
    next_body_retry_at: datetime | None


def capability_for(kind: str) -> SourceCapability:
    return SourceCapability.AUTHOR_POSTS if kind == "mp_account" else SourceCapability.SEARCH


def list_due_editorial_sources_in_transaction(
    session: Session, *, now: datetime, limit: int = 200
) -> tuple[EditorialDue, ...]:
    if not session.in_transaction() or now.utcoffset() is None or not 1 <= limit <= 200:
        raise ValueError("source due read requires a transaction, aware time and bounded limit")
    rows = session.execute(
        select(EditorialSourceProfile, EditorialSourceVersion)
        .join(
            EditorialSourceVersion,
            (EditorialSourceVersion.owner_id == EditorialSourceProfile.owner_id)
            & (EditorialSourceVersion.profile_id == EditorialSourceProfile.id)
            & (EditorialSourceVersion.version == EditorialSourceProfile.current_version),
        )
        .where(EditorialSourceProfile.enabled.is_(True), EditorialSourceVersion.kind != "external")
        .order_by(
            EditorialSourceProfile.next_fetch_at.asc().nullsfirst(), EditorialSourceProfile.id
        )
        .limit(limit)
    ).all()
    values = []
    for p, v in rows:
        unresolved = session.scalar(
            select(EditorialSourceRun.id)
            .where(
                EditorialSourceRun.owner_id == p.owner_id,
                EditorialSourceRun.profile_id == p.id,
                EditorialSourceRun.status.in_(("running", "unknown", "staged")),
            )
            .limit(1)
        )
        due = p.next_fetch_at or p.created_at
        if unresolved is None and due <= now:
            values.append(
                EditorialDue(
                    owner_id=p.owner_id,
                    profile_id=p.id,
                    source_key=p.source_key,
                    configuration_version=v.version,
                    revision=p.revision,
                    due_at=due,
                    kind=v.kind,
                )
            )
    return tuple(values)


@dataclass(frozen=True)
class AppliedEditorialMaterial:
    status: Literal["succeeded", "duplicate"]
    change: Literal["created", "revised", "unchanged"] | None
    content_id: UUID
    content_version_id: UUID


class EditorialSourceService:
    def __init__(
        self,
        session: Session,
        *,
        external_tokens: Mapping[UUID, SecretStr] | None = None,
        ingress_hmac_secret: SecretStr | None = None,
        clock: Clock = lambda: datetime.now(UTC),
    ) -> None:
        self._session, self._clock = session, clock
        self._external_tokens = external_tokens or {}
        self._ingress_hmac_secret = ingress_hmac_secret

    def list_profiles(
        self, *, owner_id: UUID, personal: bool = False
    ) -> tuple[EditorialProfileView, ...]:
        self._session.rollback()
        with self._session.begin():
            rows = self._session.scalars(
                select(EditorialSourceProfile)
                .where(
                    EditorialSourceProfile.owner_id == owner_id,
                    EditorialSourceProfile.source_key.startswith("ed_personal_", autoescape=True)
                    if personal
                    else ~EditorialSourceProfile.source_key.startswith(
                        "ed_personal_", autoescape=True
                    ),
                )
                .order_by(EditorialSourceProfile.name, EditorialSourceProfile.id)
            ).all()
            return tuple(self._view(p) for p in rows)

    def get_profile(self, *, owner_id: UUID, profile_id: UUID) -> EditorialProfileView:
        self._session.rollback()
        with self._session.begin():
            return self._view(self._profile(owner_id, profile_id))

    def list_group_backlogs(self, *, owner_id: UUID) -> tuple[EditorialGroupBacklogView, ...]:
        # Load after initialization because group orchestration also uses this service.
        from connections.editorial_group import (
            list_editorial_group_backlogs_in_transaction,
        )

        self._session.rollback()
        with self._session.begin():
            return list_editorial_group_backlogs_in_transaction(self._session, owner_id=owner_id)

    def review_group_backlog(
        self, *, owner_id: UUID, command: EditorialGroupBacklogReviewInput
    ) -> EditorialGroupBacklogReviewResult:
        # Load after initialization because group orchestration also uses this service.
        from connections.editorial_group import (
            review_editorial_group_backlog_in_transaction,
        )

        self._session.rollback()
        with self._session.begin():
            return review_editorial_group_backlog_in_transaction(
                self._session, owner_id=owner_id, command=command, now=self._clock()
            )

    def enqueue_poll(
        self, *, owner_id: UUID, profile_id: UUID, command: EditorialPollInput
    ) -> JobView:
        self._session.rollback()
        with self._session.begin():
            return self.enqueue_poll_in_transaction(
                owner_id=owner_id, profile_id=profile_id, command=command, audited=True
            )

    def enqueue_poll_in_transaction(
        self,
        *,
        owner_id: UUID,
        profile_id: UUID,
        command: EditorialPollInput,
        audited: bool = False,
        scheduled_for_at: datetime | None = None,
    ) -> JobView:
        if not self._session.in_transaction():
            raise RuntimeError("source Job admission requires caller transaction")
        p = self._profile(owner_id, profile_id, lock=True)
        v = self._version(p)
        if audited:
            accept_audit_in_transaction(
                self._session,
                owner_id=owner_id,
                operation_id=command.operation_id,
                action="editorial_source.poll",
                target_ref=f"editorial-source:{p.id}",
                reason=command.reason,
                payload=command.model_dump(mode="json"),
                now=self._clock(),
                before_state={"revision": p.revision, "configuration_version": v.version},
            )
            frozen = load_completed_audit_in_transaction(
                self._session,
                owner_id=owner_id,
                operation_id=command.operation_id,
            )
            if frozen is not None:
                return JobView.model_validate(frozen)
        if p.revision != command.expected_revision or not p.enabled:
            raise ApplicationError("editorial_version_conflict")
        if v.kind == "external":
            raise ApplicationError("invalid_editorial_input")
        if self._has_unresolved(p):
            raise ApplicationError("editorial_version_conflict")
        self._require_ready(p, v, self._clock())
        if audited:
            accept_audit_in_transaction(
                self._session,
                owner_id=owner_id,
                operation_id=command.operation_id,
                action="editorial_source.poll",
                target_ref=f"editorial-source:{p.id}",
                reason=command.reason,
                payload=command.model_dump(mode="json"),
                now=self._clock(),
                before_state={"revision": p.revision, "configuration_version": v.version},
            )
        result = JobService(self._session, clock=self._clock).accept_in_transaction(
            owner_id=owner_id,
            command=JobAcceptanceInput(
                operation_id=command.operation_id,
                kind="source.editorial.poll",
                observation=JobObservationContext(
                    configuration_ref=f"editorial-source:{p.id}",
                    configuration_version=v.version,
                    source_key=p.source_key,
                    source_capability=capability_for(v.kind),
                ),
                scheduled_for_at=scheduled_for_at,
                scope={"profile_id": str(p.id), "revision": p.revision},
            ),
        )
        if audited:
            complete_audit_in_transaction(
                self._session,
                owner_id=owner_id,
                operation_id=command.operation_id,
                after_state=result.model_dump(mode="json"),
                now=self._clock(),
            )
        return result

    def save_profile(
        self,
        *,
        owner_id: UUID,
        command: EditorialProfileInput,
        profile_id: UUID | None = None,
        personal: bool = False,
    ) -> EditorialProfileView:
        self._session.rollback()
        try:
            with self._session.begin():
                return self.save_profile_in_transaction(
                    owner_id=owner_id, command=command, profile_id=profile_id, personal=personal
                )
        except (SourceAccessUnavailableError, RetentionPolicyUnavailableError) as error:
            if not personal:
                raise
            raise ApplicationError(
                "editorial_source_unavailable", context={"reason": "source_policy_unavailable"}
            ) from error

    def approve_rsshub(
        self, *, owner_id: UUID, profile_id: UUID, command: EditorialRsshubApprovalInput
    ) -> EditorialRsshubApprovalView:
        self._session.rollback()
        with self._session.begin():
            return approve_editorial_rsshub_profile_in_transaction(
                self._session,
                owner_id=owner_id,
                profile_id=profile_id,
                command=command,
                now=self._clock(),
            )

    def approve_body(
        self, *, owner_id: UUID, profile_id: UUID, command: EditorialBodyApprovalInput
    ) -> EditorialBodyApprovalView:
        self._session.rollback()
        with self._session.begin():
            return approve_editorial_body_profile_in_transaction(
                self._session,
                owner_id=owner_id,
                profile_id=profile_id,
                command=command,
                now=self._clock(),
            )

    def save_profile_in_transaction(
        self,
        *,
        owner_id: UUID,
        command: EditorialProfileInput,
        profile_id: UUID | None = None,
        personal: bool = False,
    ) -> EditorialProfileView:
        if not self._session.in_transaction():
            raise RuntimeError("editorial operator writes require caller transaction")
        digest = fingerprint(command.model_dump(mode="json"))
        replay = self._session.scalar(
            select(EditorialSourceVersion).where(
                EditorialSourceVersion.owner_id == owner_id,
                EditorialSourceVersion.operation_id == command.operation_id,
            )
        )
        if replay is not None:
            if replay.input_hash != digest or (
                profile_id is not None and replay.profile_id != profile_id
            ):
                raise ApplicationError("idempotency_conflict")
            profile = self._profile(owner_id, replay.profile_id)
            if personal != profile.source_key.startswith("ed_personal_"):
                raise ApplicationError("resource_not_found")
            return self._view(profile)
        now = self._clock()
        before_state: dict[str, object] = {"configured": False}
        if profile_id is None:
            if command.expected_revision != 0 or command.enabled:
                raise ApplicationError("invalid_editorial_input")
            require_unique_rsshub_target_in_transaction(
                self._session, owner_id=owner_id, configuration=command.configuration
            )
            profile_id = uuid4()
            p = EditorialSourceProfile(
                id=profile_id,
                owner_id=owner_id,
                source_key=(
                    f"{'ed_personal' if personal else 'ed'}_"
                    f"{command.configuration.kind}_{profile_id.hex}"
                ),
                name=command.name,
                enabled=False,
                current_version=1,
                revision=1,
                cursor=EditorialCursor().model_dump(mode="json"),
                health="unknown",
                failure_count=0,
                last_failure_code=None,
                last_fetch_at=None,
                last_ok_at=None,
                next_fetch_at=None,
                created_at=now,
                updated_at=now,
            )
            self._session.add(p)
            self._session.flush()
        else:
            p = self._profile(owner_id, profile_id, lock=True)
            if personal != p.source_key.startswith("ed_personal_"):
                raise ApplicationError("resource_not_found")
            old = self._version(p)
            before_state = self._view(p).model_dump(mode="json")
            if p.revision != command.expected_revision:
                raise ApplicationError("editorial_version_conflict")
            if old.kind != command.configuration.kind:
                raise ApplicationError("invalid_editorial_input")
            if self._has_unresolved(p):
                raise ApplicationError("editorial_version_conflict")
            require_unique_rsshub_target_in_transaction(
                self._session,
                owner_id=owner_id,
                configuration=command.configuration,
                profile_id=p.id,
            )
            p.current_version += 1
            p.revision += 1
            p.name, p.enabled, p.updated_at = command.name, command.enabled, now
            # A changed parsing contract invalidates conditional RSS validators.
            p.cursor = (
                EditorialCursor.model_validate(p.cursor)
                .model_copy(update={"rss": None})
                .model_dump(mode="json")
            )
        # A returned profile carries its own gate's *previous* version. Validate
        # that frozen input before rotating the gate for this configuration.
        # Externally bound X/MP connections keep their supplied version unchanged.
        own_gate_binding = False
        if command.connection_id is not None:
            supplied = self._session.scalar(
                select(SourceConnection)
                .where(
                    SourceConnection.owner_id == owner_id,
                    SourceConnection.id == command.connection_id,
                )
                .with_for_update()
            )
            supplied_version = self._session.get(
                SourceConnectionVersion,
                (command.connection_id, command.connection_version),
            )
            if (
                supplied is None
                or supplied_version is None
                or supplied_version.owner_id != owner_id
                or supplied.current_version != command.connection_version
            ):
                raise ApplicationError("connection_version_conflict")
            own_gate_binding = supplied.source_key == p.source_key
        gate = self._gate(p, command, now)
        connection_id = command.connection_id or gate.id
        connection_version = (
            gate.current_version
            if own_gate_binding or command.connection_version is None
            else command.connection_version
        )
        bound = self._session.scalar(
            select(SourceConnection)
            .where(SourceConnection.owner_id == owner_id, SourceConnection.id == connection_id)
            .with_for_update()
        )
        version = self._session.get(SourceConnectionVersion, (connection_id, connection_version))
        if (
            bound is None
            or version is None
            or version.owner_id != owner_id
            or bound.current_version != connection_version
        ):
            raise ApplicationError("connection_version_conflict")
        if command.enabled and bound.status != "active":
            raise ApplicationError("connection_disabled")
        if command.configuration.kind == "x_search" and (
            bound.source_key != "x" or version.auth_kind != "server_credential"
        ):
            raise ApplicationError("invalid_editorial_input")
        if command.configuration.kind == "mp_account" and version.auth_kind != "server_credential":
            raise ApplicationError("invalid_editorial_input")
        v = EditorialSourceVersion(
            profile_id=p.id,
            version=p.current_version,
            owner_id=owner_id,
            operation_id=command.operation_id,
            input_hash=digest,
            kind=command.configuration.kind,
            configuration=command.configuration.model_dump(mode="json"),
            participation_mode=command.participation_mode,
            tier=command.tier,
            first_party=command.first_party,
            connection_id=connection_id,
            connection_version=connection_version,
            policy_version=command.policy_version,
            interval_minutes=command.interval_minutes,
            created_at=now,
        )
        self._session.add(v)
        self._session.flush()
        if command.enabled:
            self._require_ready(p, v, now)
            p.next_fetch_at = now
        editorial = EditorialService(self._session, clock=self._clock)
        linked = editorial.get_source_in_transaction(owner_id=owner_id, source_key=p.source_key)
        synced = EditorialSourceInput(
            operation_id=uuid5(command.operation_id, "analysis-source"),
            expected_revision=linked.revision if linked else 0,
            name=p.name,
            source_kind=cast(SourceKind, v.kind),
            tier=cast(Tier, "UNGRADED" if v.tier == "T3" else v.tier),
            first_party=v.first_party,
            owner_entity_id=linked.owner_entity_id if linked else None,
            tags=linked.tags if linked else [],
            enabled=p.enabled and v.participation_mode == "editorial",
        )
        if linked is None or synced.model_dump(
            exclude={"operation_id", "expected_revision"}
        ) != linked.model_dump(exclude={"source_key", "revision"}):
            editorial.save_source_in_transaction(
                owner_id=owner_id, source_key=p.source_key, command=synced
            )
        result = self._view(p)
        accept_audit_in_transaction(
            self._session,
            owner_id=owner_id,
            operation_id=command.operation_id,
            action="editorial_source.configure",
            target_ref=f"editorial-source:{p.id}",
            reason=command.reason,
            payload=command.model_dump(mode="json"),
            now=now,
            before_state=before_state,
        )
        complete_audit_in_transaction(
            self._session,
            owner_id=owner_id,
            operation_id=command.operation_id,
            after_state=result.model_dump(mode="json"),
            now=now,
        )
        return result

    def _gate(
        self, p: EditorialSourceProfile, command: EditorialProfileInput, now: datetime
    ) -> SourceConnection:
        gate = self._session.scalar(
            select(SourceConnection)
            .where(
                SourceConnection.owner_id == p.owner_id, SourceConnection.source_key == p.source_key
            )
            .with_for_update()
        )
        if gate is None:
            gate = SourceConnection(
                id=uuid4(),
                owner_id=p.owner_id,
                source_key=p.source_key,
                status="disabled",
                current_version=1,
                safety_events=[],
                created_at=now,
                updated_at=now,
            )
            self._session.add(gate)
            self._session.flush()
        else:
            gate.current_version += 1
        gate.status = "active" if command.enabled else "disabled"
        gate.updated_at = now
        self._session.add(
            SourceConnectionVersion(
                connection_id=gate.id,
                version=gate.current_version,
                owner_id=p.owner_id,
                auth_kind="none",
                secret_ref=None,
                config={"allowed_hosts": list(command.configuration.allowed_hosts)},
                execution_policy=(
                    rsshub_execution_policy(command.configuration).model_dump(mode="json")
                    if command.configuration.rsshub
                    else None
                ),
                created_by=p.owner_id,
                created_at=now,
            )
        )
        self._session.flush()
        return gate

    def list_runs(
        self, *, owner_id: UUID, profile_id: UUID, limit: int = 50
    ) -> tuple[EditorialRunResult, ...]:
        if not 1 <= limit <= 100:
            raise ApplicationError("invalid_editorial_input")
        self._session.rollback()
        with self._session.begin():
            self._profile(owner_id, profile_id)
            rows = self._session.scalars(
                select(EditorialSourceRun)
                .where(
                    EditorialSourceRun.owner_id == owner_id,
                    EditorialSourceRun.profile_id == profile_id,
                )
                .order_by(EditorialSourceRun.created_at.desc(), EditorialSourceRun.id)
                .limit(limit)
            ).all()
            return tuple(self._result(r) for r in rows)

    def verify_external_token(self, *, owner_id: UUID, profile_id: UUID, token: str | None) -> None:
        expected = self._external_tokens.get(profile_id)
        if expected is None:
            raise ApplicationError("external_source_disabled")
        if (
            token is None
            or len(token.encode()) > 4096
            or not compare_digest(token.encode(), expected.get_secret_value().encode())
        ):
            raise ApplicationError("external_source_authentication_required")
        # The authenticated partition is still checked before admitting a payload.
        p = self.get_profile(owner_id=owner_id, profile_id=profile_id)
        if p.configuration.kind != "external" or not p.enabled:
            raise ApplicationError("editorial_source_disabled")

    def accept_external(
        self,
        *,
        owner_id: UUID,
        profile_id: UUID,
        command: ExternalEditorialInput,
        peer_hash: str | None = None,
    ) -> JobView:
        self._session.rollback()
        with self._session.begin():
            p = self._profile(owner_id, profile_id, lock=True)
            v = self._version(p)
            if v.kind != "external" or not p.enabled:
                raise ApplicationError("editorial_source_disabled")
            existing = self._session.scalar(
                select(EditorialSourceRun).where(
                    EditorialSourceRun.owner_id == owner_id,
                    EditorialSourceRun.profile_id == profile_id,
                    EditorialSourceRun.operation_id == command.operation_id,
                )
            )
            digest = fingerprint(command.model_dump(mode="json"))
            if existing is not None and existing.input_hash != digest:
                raise ApplicationError("idempotency_conflict")
            if existing is None and (
                p.revision != command.expected_revision
                or p.current_version != command.configuration_version
            ):
                raise ApplicationError("editorial_version_conflict")
            self._require_ready(p, v, self._clock())
            if existing is None and peer_hash is not None:
                require_external_ingress_rate_in_transaction(
                    self._session, owner_id=owner_id, peer_hash=peer_hash, now=self._clock()
                )
            frozen = (
                load_job_execution_configuration(self._session, job_id=existing.job_id)
                if existing is not None
                else None
            )
            job = JobService(self._session, clock=self._clock).accept_in_transaction(
                owner_id=owner_id,
                command=JobAcceptanceInput(
                    operation_id=command.operation_id,
                    kind="source.editorial.ingest",
                    observation=JobObservationContext(
                        configuration_ref=f"editorial-source:{p.id}",
                        configuration_version=command.configuration_version,
                        source_key=p.source_key,
                        source_capability=capability_for(v.kind),
                    ),
                    scope=frozen.scope
                    if frozen is not None
                    else {
                        "profile_id": str(p.id),
                        "revision": command.expected_revision,
                        "input_hash": digest.hex(),
                        **({"ingress_peer_hash": peer_hash} if peer_hash is not None else {}),
                    },
                ),
            )
            if existing is None:
                from connections.external_ingress import prepare_external_materials

                now = self._clock()
                materials, items = prepare_external_materials(command.materials)
                cursor = EditorialCursor.model_validate(p.cursor).model_copy(
                    update={
                        "initialized_at": EditorialCursor.model_validate(p.cursor).initialized_at
                        or now,
                        "last_ok_at": now,
                    }
                )
                page = EditorialPage(
                    status="complete", materials=materials, cursor=cursor, observed_at=now
                )
                self._session.add(
                    EditorialSourceRun(
                        id=uuid4(),
                        owner_id=owner_id,
                        profile_id=p.id,
                        operation_id=command.operation_id,
                        input_hash=digest,
                        configuration_version=v.version,
                        profile_revision=p.revision,
                        job_id=job.id,
                        status="staged",
                        prepared_page={
                            **page.model_dump(mode="json"),
                            "external_items": [item.model_dump(mode="json") for item in items],
                        },
                        found=len(command.materials),
                        created=0,
                        revised=0,
                        failure_code=None,
                        review_audit=None,
                        created_at=now,
                        updated_at=now,
                    )
                )
            return job

    def accept_ingress(
        self,
        *,
        owner_id: UUID,
        profile_id: UUID,
        command: ExternalEditorialInput,
        peer_ip: str | None,
    ) -> ExternalIngressReceipt:
        if self._ingress_hmac_secret is None or peer_ip is None:
            raise ApplicationError("external_source_disabled")
        try:
            peer = ip_address(peer_ip).compressed
        except ValueError:
            raise ApplicationError("external_source_disabled") from None
        peer_hash = hmac_new(
            self._ingress_hmac_secret.get_secret_value().encode(), peer.encode(), "sha256"
        ).hexdigest()
        try:
            job = self.accept_external(
                owner_id=owner_id, profile_id=profile_id, command=command, peer_hash=peer_hash
            )
        except (SourceAccessUnavailableError, RetentionPolicyUnavailableError):
            raise ApplicationError("external_source_disabled") from None
        self._session.rollback()
        with self._session.begin():
            run = self._session.scalar(
                select(EditorialSourceRun).where(
                    EditorialSourceRun.owner_id == owner_id,
                    EditorialSourceRun.profile_id == profile_id,
                    EditorialSourceRun.job_id == job.id,
                )
            )
            if run is None:
                raise ApplicationError("resource_not_found")
            return self._ingress_receipt_in_transaction(run)

    def get_ingress_receipt(
        self, *, owner_id: UUID, profile_id: UUID, run_id: UUID
    ) -> ExternalIngressReceipt:
        self._session.rollback()
        with self._session.begin():
            profile = self._profile(owner_id, profile_id)
            version = self._version(profile)
            if version.kind != "external":
                raise ApplicationError("resource_not_found")
            try:
                self._require_ready(profile, version, self._clock())
            except (SourceAccessUnavailableError, RetentionPolicyUnavailableError):
                raise ApplicationError("external_source_disabled") from None
            run = self._session.scalar(
                select(EditorialSourceRun).where(
                    EditorialSourceRun.owner_id == owner_id,
                    EditorialSourceRun.profile_id == profile_id,
                    EditorialSourceRun.id == run_id,
                )
            )
            if run is None:
                raise ApplicationError("resource_not_found")
            return self._ingress_receipt_in_transaction(run)

    def _ingress_receipt_in_transaction(self, run: EditorialSourceRun) -> ExternalIngressReceipt:
        job = load_external_ingress_job_in_transaction(
            self._session, owner_id=run.owner_id, job_id=run.job_id
        )
        if job is None or run.prepared_page is None:
            raise ApplicationError("resource_not_found")
        items = tuple(
            ExternalIngressItem.model_validate(item)
            for item in cast(list[object], run.prepared_page.get("external_items", []))
        )
        return ExternalIngressReceipt(
            job=job,
            profile_id=run.profile_id,
            run_id=run.id,
            configuration_version=run.configuration_version,
            received=len(items),
            items=items,
        )

    def begin_run(
        self,
        *,
        owner_id: UUID,
        profile_id: UUID,
        configuration_version: int,
        revision: int,
        job_id: UUID,
        operation_id: UUID,
        guard: Guard | None = None,
    ) -> PreparedEditorialRun:
        self._session.rollback()
        with self._session.begin():
            return self._begin_run_in_transaction(
                owner_id=owner_id,
                profile_id=profile_id,
                configuration_version=configuration_version,
                revision=revision,
                job_id=job_id,
                operation_id=operation_id,
                guard=guard,
            )

    def _begin_run_in_transaction(
        self,
        *,
        owner_id: UUID,
        profile_id: UUID,
        configuration_version: int,
        revision: int,
        job_id: UUID,
        operation_id: UUID,
        guard: Guard | None = None,
    ) -> PreparedEditorialRun:
        if not self._session.in_transaction():
            raise RuntimeError("source run admission requires caller transaction")
        p = self._profile(owner_id, profile_id, lock=True)
        v = self._version(p)
        profile = self._view(p)
        known = {
            r.identity_key: KnownMaterial(
                r.body_status,
                r.body_retry_count,
                r.published_at,
                r.created_at,
                r.detail_title,
                r.next_body_retry_at,
            )
            for r in self._session.scalars(
                select(EditorialSourceMaterialReceipt).where(
                    EditorialSourceMaterialReceipt.owner_id == owner_id,
                    EditorialSourceMaterialReceipt.profile_id == profile_id,
                )
            )
        }
        cursor = EditorialCursor.model_validate(p.cursor)
        run = self._session.scalar(
            select(EditorialSourceRun)
            .where(
                EditorialSourceRun.owner_id == owner_id,
                EditorialSourceRun.profile_id == profile_id,
                EditorialSourceRun.operation_id == operation_id,
            )
            .with_for_update()
        )
        digest = fingerprint(
            {
                "profile_id": str(profile_id),
                "configuration_version": configuration_version,
                "revision": revision,
                "job_id": str(job_id),
            }
        )
        if run is not None:
            if (
                run.job_id != job_id
                or run.configuration_version != configuration_version
                or run.profile_revision != revision
                or (v.kind != "external" and run.input_hash != digest)
            ):
                raise ApplicationError("idempotency_conflict")
            if run.status == "running":
                # Durable running means a previous provider boundary may have crossed.
                run.status, run.failure_code, run.updated_at = (
                    "unknown",
                    "abandoned_source_request",
                    self._clock(),
                )
            page = (
                EditorialPage.model_validate(
                    {
                        key: value
                        for key, value in run.prepared_page.items()
                        if key not in {"external_items", "_body_phase"}
                    }
                )
                if run.status == "staged" and run.prepared_page
                else None
            )
            return PreparedEditorialRun(
                self._result(run),
                profile,
                cursor,
                cast(Mapping[str, EditorialKnownMaterial], known),
                page,
                False,
                p.created_at,
            )
        if not p.enabled:
            raise ApplicationError("editorial_source_disabled")
        if (
            p.current_version != configuration_version
            or p.revision != revision
            or self._has_unresolved(p)
        ):
            raise ApplicationError("editorial_version_conflict")
        if guard is not None and not guard(self._session, owner_id, job_id):
            raise ApplicationError("editorial_version_conflict")
        context = load_content_job_context_for_editorial_member_in_transaction(
            self._session, owner_id=owner_id, job_id=job_id, profile_id=profile_id
        ) or load_content_job_context(self._session, owner_id=owner_id, job_id=job_id)
        if (
            context is None
            or context.source_key != p.source_key
            or context.configuration_version != configuration_version
            or context.configuration_ref != f"editorial-source:{profile_id}"
            or context.source_capability != capability_for(v.kind)
        ):
            raise ApplicationError("resource_not_found")
        self._require_ready(p, v, self._clock())
        now = self._clock()
        run = EditorialSourceRun(
            id=uuid4(),
            owner_id=owner_id,
            profile_id=profile_id,
            operation_id=operation_id,
            input_hash=digest,
            configuration_version=configuration_version,
            profile_revision=revision,
            job_id=job_id,
            status="running",
            prepared_page=None,
            found=0,
            created=0,
            revised=0,
            failure_code=None,
            review_audit=None,
            created_at=now,
            updated_at=now,
        )
        self._session.add(run)
        p.last_fetch_at, p.updated_at = now, now
        self._session.flush()
        return PreparedEditorialRun(
            self._result(run),
            profile,
            cursor,
            cast(Mapping[str, EditorialKnownMaterial], known),
            None,
            v.kind != "external",
            p.created_at,
        )

    def stage_page(
        self, *, owner_id: UUID, run_id: UUID, page: EditorialPage, guard: Guard | None = None
    ) -> EditorialRunResult:
        self._session.rollback()
        with self._session.begin():
            run, p, v = self._current_run(owner_id, run_id, guard)
            if run.status != "running":
                raise ApplicationError("editorial_version_conflict")
            body = self._view(p).configuration.body_extraction
            page_limit = (6 if body is not None and body.enabled else 8) * 1024 * 1024
            if len(page.model_dump_json().encode()) > page_limit:
                raise ApplicationError("invalid_editorial_input")
            if page.status in {"unknown", "blocked"}:
                run.status = page.status
                run.prepared_page = (
                    page.model_dump(mode="json") if page.status == "unknown" else None
                )
                run.failure_code = page.reason
                self._failure_health(
                    p, v, page.reason, self._clock(), unknown=page.status == "unknown"
                )
            elif page.status == "partial" and not page.materials and not page.cursor.x_backlog:
                run.status, run.failure_code = "failed", page.reason
                self._failure_health(p, v, page.reason, self._clock(), unknown=False)
            else:
                run.status = "staged"
                run.prepared_page = page.model_dump(mode="json")
            run.found, run.updated_at = len(page.materials), self._clock()
            return self._result(run)

    def apply_page(
        self, *, owner_id: UUID, run_id: UUID, guard: Guard | None = None, sink: Sink | None = None
    ) -> EditorialRunResult:
        self._session.rollback()
        with self._session.begin():
            run, p, v = self._current_run(owner_id, run_id, guard)
            if run.status in {"succeeded", "partial"}:
                return self._result(run)
            if run.status != "staged" or run.prepared_page is None:
                return self._result(run)
            page = EditorialPage.model_validate(
                {
                    key: value
                    for key, value in run.prepared_page.items()
                    if key not in {"external_items", "_body_phase"}
                }
            )
            self._require_ready(p, v, self._clock())
            if v.kind == "external":
                from connections.external_ingress import apply_external_page_in_transaction

                return apply_external_page_in_transaction(
                    self, run=run, profile=p, version=v, page=page, guard=guard, sink=sink
                )
            if "_body_phase" in run.prepared_page:
                return self._result(run)
            first = EditorialCursor.model_validate(p.cursor).initialized_at is None
            body = self._view(p).configuration.body_extraction
            targets: list[EditorialBodyTarget] = []
            overflow = False
            seen: set[str] = set()
            for material in page.materials:
                if material.identity_key in seen:
                    continue
                seen.add(material.identity_key)
                applied = self._apply_material_in_transaction(
                    p=p, v=v, run=run, page=page, first=first, material=material, sink=sink
                )
                if (
                    applied.status != "duplicate"
                    and body is not None
                    and body.enabled
                    and material.body_status != "ok"
                ):
                    target = load_editorial_body_target_in_transaction(
                        self._session,
                        owner_id=owner_id,
                        run_id=run.id,
                        profile_id=p.id,
                        configuration_version=v.version,
                        profile_revision=p.revision,
                        job_id=run.job_id,
                        operation_id=run.operation_id,
                        content_id=applied.content_id,
                        content_version_id=applied.content_version_id,
                        material=material,
                        now=self._clock(),
                    )
                    if target is not None:
                        if len(targets) < body.max_fetches:
                            targets.append(target)
                        else:
                            overflow = True
            if targets or overflow:
                phase = EditorialBodyCheckpoint(
                    targets=tuple(targets), failure_codes=("body_target_limit",) if overflow else ()
                )
                self._save_body_checkpoint(run, phase)
                return self._result(run)
            return self._complete_page_in_transaction(run=run, p=p, v=v, page=page)

    def _complete_page_in_transaction(
        self,
        *,
        run: EditorialSourceRun,
        p: EditorialSourceProfile,
        v: EditorialSourceVersion,
        page: EditorialPage,
    ) -> EditorialRunResult:
        # Failed coverage never becomes an advanced cursor; known content remains useful.
        now = self._clock()
        if page.status in {"complete", "unchanged"}:
            p.cursor = page.cursor.model_dump(mode="json")
            p.last_ok_at, p.health, p.failure_count, p.last_failure_code = now, "ok", 0, None
            run.status = "succeeded"
            record_source_fetch_success_in_transaction(
                self._session,
                owner_id=run.owner_id,
                source_key=p.source_key,
                selector_kind="source",
                selector_ref=p.source_key,
                completed_at=now,
            )
            p.next_fetch_at = now + timedelta(minutes=v.interval_minutes)
        else:
            run.status, run.failure_code = "partial", page.reason
            if v.kind in {"x_search", "mp_account"}:
                # Preserve exact unfinished query/token lineage while keeping coverage old.
                old_cursor = EditorialCursor.model_validate(p.cursor)
                p.cursor = page.cursor.model_copy(
                    update={"last_ok_at": old_cursor.last_ok_at}
                ).model_dump(mode="json")
            self._failure_health(p, v, page.reason, now, unknown=False)
        p.updated_at, run.updated_at = now, now
        phase_data = (run.prepared_page or {}).get("_body_phase")
        if phase_data is not None:
            phase = EditorialBodyCheckpoint.model_validate_json(json.dumps(phase_data))
            # Terminal facts retain references/counters only, never a second body cache.
            run.prepared_page = {
                "_body_receipt": {
                    "feed_observation_ids": [str(t.feed_observation_id) for t in phase.targets],
                    "body_observation_ids": [str(item) for item in phase.completed_observation_ids],
                    "local_collector_calls": phase.local_collector_calls,
                    "target_request_count": phase.target_request_count,
                    "failure_codes": list(phase.failure_codes),
                }
            }
        else:
            run.prepared_page = None
        if page.filtered:
            run.prepared_page = {
                **(run.prepared_page or {}),
                "_filter_receipt": {"filtered": page.filtered},
            }
        return self._result(run)

    def body_checkpoint(
        self, *, owner_id: UUID, run_id: UUID, guard: Guard | None = None
    ) -> EditorialBodyCheckpoint | None:
        self._session.rollback()
        with self._session.begin():
            run, _, _ = self._current_run(owner_id, run_id, guard)
            if (
                run.status != "staged"
                or not run.prepared_page
                or "_body_phase" not in run.prepared_page
            ):
                return None
            return EditorialBodyCheckpoint.model_validate_json(
                json.dumps(run.prepared_page["_body_phase"])
            )

    def begin_body_request(
        self, *, owner_id: UUID, run_id: UUID, guard: Guard | None = None
    ) -> EditorialBodyTarget:
        self._session.rollback()
        with self._session.begin():
            run, p, v, phase = self._current_body(owner_id, run_id, guard)
            if phase.request_pending or phase.next_index >= len(phase.targets):
                raise ApplicationError("editorial_version_conflict")
            target = phase.targets[phase.next_index]
            self._require_ready(p, v, self._clock())
            require_editorial_body_input_in_transaction(
                self._session, target=target, now=self._clock()
            )
            self._save_body_checkpoint(run, phase.model_copy(update={"request_pending": True}))
            return target

    def apply_body_response(
        self, *, owner_id: UUID, run_id: UUID, response: WebPageResult, guard: Guard | None = None
    ) -> None:
        self._session.rollback()
        with self._session.begin():
            run, p, v, phase = self._current_body(owner_id, run_id, guard)
            if not phase.request_pending or phase.next_index >= len(phase.targets):
                raise ApplicationError("editorial_version_conflict")
            target = phase.targets[phase.next_index]
            self._require_ready(p, v, self._clock())
            completed, failures = phase.completed_observation_ids, phase.failure_codes
            if response.document is not None:
                require_editorial_body_execution_in_transaction(
                    self._session,
                    owner_id=owner_id,
                    profile_id=p.id,
                    configuration_version=v.version,
                    revision=p.revision,
                    now=self._clock(),
                )
                if v.connection_id is None or v.connection_version is None:
                    raise ApplicationError("connection_disabled")
                saved = self._session.scalar(
                    select(EditorialSourceMaterialReceipt)
                    .where(
                        EditorialSourceMaterialReceipt.owner_id == owner_id,
                        EditorialSourceMaterialReceipt.profile_id == p.id,
                        EditorialSourceMaterialReceipt.identity_key == target.material.identity_key,
                    )
                    .with_for_update()
                )
                if (
                    saved is None
                    or saved.content_id != target.content_id
                    or saved.content_version_id != target.expected_content_version_id
                ):
                    raise ApplicationError("editorial_version_conflict")
                result = complete_editorial_body_in_transaction(
                    self._session,
                    target=target,
                    document=response.document,
                    source_key=p.source_key,
                    capability=capability_for(v.kind),
                    policy_version=v.policy_version,
                    connection_id=v.connection_id,
                    connection_version=v.connection_version,
                    now=self._clock(),
                )
                saved.content_version_id = result.content_version_id
                saved.observation_id = result.observation_id
                saved.body_status, saved.updated_at = (
                    ("ok" if response.document.text_scope == "full" else "pending"),
                    self._clock(),
                )
                saved.run_id = run.id
                # Keep the feed hash: identical feed replay must not replace a completed body.
                completed += (result.observation_id,)
                run.revised += 1
            else:
                reason = (
                    response.stop_reason.value if response.stop_reason is not None else "unknown"
                )
                failures += (f"body_{reason}"[:64],)
            self._save_body_checkpoint(
                run,
                phase.model_copy(
                    update={
                        "next_index": phase.next_index + 1,
                        "request_pending": False,
                        "completed_observation_ids": completed,
                        "failure_codes": failures,
                        "local_collector_calls": phase.local_collector_calls
                        + response.collector_call_count,
                    }
                ),
            )

    def finish_body_phase(
        self, *, owner_id: UUID, run_id: UUID, guard: Guard | None = None
    ) -> EditorialRunResult:
        self._session.rollback()
        with self._session.begin():
            run, p, v, phase = self._current_body(owner_id, run_id, guard)
            if phase.request_pending:
                # No result after a durable request boundary: do not repeat an unknown request.
                run.status, run.failure_code, run.updated_at = (
                    "unknown",
                    "abandoned_body_request",
                    self._clock(),
                )
                self._failure_health(p, v, run.failure_code, self._clock(), unknown=True)
                return self._result(run)
            if phase.request_pending or phase.next_index < len(phase.targets):
                raise ApplicationError("editorial_version_conflict")
            assert run.prepared_page is not None
            page = EditorialPage.model_validate(
                {
                    k: value
                    for k, value in run.prepared_page.items()
                    if k not in {"external_items", "_body_phase"}
                }
            )
            body = self._view(p).configuration.body_extraction
            if phase.failure_codes and body is not None and body.required:
                page = page.model_copy(
                    update={"status": "partial", "reason": phase.failure_codes[0]}
                )
            return self._complete_page_in_transaction(run=run, p=p, v=v, page=page)

    def _current_body(
        self,
        owner_id: UUID,
        run_id: UUID,
        guard: Guard | None,
    ) -> tuple[
        EditorialSourceRun, EditorialSourceProfile, EditorialSourceVersion, EditorialBodyCheckpoint
    ]:
        run, p, v = self._current_run(owner_id, run_id, guard)
        state = load_job_cancellation_state_in_transaction(
            self._session, owner_id=owner_id, job_id=run.job_id
        )
        if (
            run.status != "staged"
            or not run.prepared_page
            or "_body_phase" not in run.prepared_page
            or state is None
            or state.status not in {JobStatus.QUEUED, JobStatus.RUNNING}
            or state.requested_at is not None
        ):
            raise ApplicationError("editorial_version_conflict")
        return (
            run,
            p,
            v,
            EditorialBodyCheckpoint.model_validate_json(
                json.dumps(run.prepared_page["_body_phase"])
            ),
        )

    def _save_body_checkpoint(
        self, run: EditorialSourceRun, phase: EditorialBodyCheckpoint
    ) -> None:
        assert run.prepared_page is not None
        value = {**run.prepared_page, "_body_phase": phase.model_dump(mode="json")}
        if len(json.dumps(value).encode()) > 8 * 1024 * 1024:
            raise ApplicationError("invalid_editorial_input")
        run.prepared_page = value
        run.updated_at = self._clock()

    def _apply_material_in_transaction(
        self,
        *,
        p: EditorialSourceProfile,
        v: EditorialSourceVersion,
        run: EditorialSourceRun,
        page: EditorialPage,
        first: bool,
        material: EditorialMaterial,
        sink: Sink | None,
    ) -> AppliedEditorialMaterial:
        owner_id = run.owner_id
        saved = self._session.get(
            EditorialSourceMaterialReceipt, (owner_id, p.id, material.identity_key)
        )
        digest = fingerprint(material.model_dump(mode="json"))
        if saved is not None and saved.material_hash == digest:
            return AppliedEditorialMaterial(
                "duplicate", None, saved.content_id, saved.content_version_id
            )
        previous_version = saved.content_version_id if saved is not None else None
        execution = (
            load_job_execution_configuration(self._session, job_id=run.job_id)
            if v.kind == "rss"
            else None
        )
        command = EditorialContentInput(
            profile_id=p.id,
            source_key=p.source_key,
            configuration_version=v.version,
            policy_version=v.policy_version,
            connection_id=v.connection_id,
            connection_version=v.connection_version,
            job_id=run.job_id,
            operation_id=run.operation_id,
            capability=capability_for(v.kind),
            observed_at=page.observed_at,
            first_import=first,
            grouped_job=load_editorial_group_manifest_in_transaction(
                self._session, owner_id=owner_id, job_id=run.job_id
            )
            is not None,
            material=material,
            identity_proof=verify_editorial_native_identity(
                material,
                configuration=EditorialSourceConfiguration.model_validate(v.configuration),
            )
            # First-version proof authority is a single-profile poll. Grouped
            # or other original Jobs retain their existing profile-scoped path.
            if execution is not None and execution.kind == "source.editorial.poll"
            else None,
        )
        ingested = (
            sink(self._session, owner_id, command)
            if sink
            else EditorialContentIngestService(
                self._session, clock=self._clock
            ).ingest_in_transaction(owner_id=owner_id, command=command)
        )
        now = self._clock()
        if saved is None:
            saved = EditorialSourceMaterialReceipt(
                owner_id=owner_id,
                profile_id=p.id,
                identity_key=material.identity_key,
                material_hash=digest,
                content_id=ingested.content_id,
                content_version_id=ingested.content_version_id,
                observation_id=ingested.observation_id,
                run_id=run.id,
                body_status=material.body_status,
                body_retry_count=0,
                first_import=first,
                detail_title=None,
                published_at=material.published_at,
                source_updated_at=material.source_updated_at,
                next_body_retry_at=None,
                material_metadata={},
                created_at=now,
                updated_at=now,
            )
            self._session.add(saved)
            run.created += 1
        else:
            if saved.content_version_id != ingested.content_version_id:
                run.revised += 1
            (
                saved.material_hash,
                saved.content_id,
                saved.content_version_id,
                saved.observation_id,
                saved.run_id,
            ) = (
                digest,
                ingested.content_id,
                ingested.content_version_id,
                ingested.observation_id,
                run.id,
            )
            saved.body_status, saved.updated_at = material.body_status, now
        detail_title = material.metadata.get("detail_title")
        if isinstance(detail_title, str):
            saved.detail_title = detail_title
        retry = material.metadata.get("body_retry")
        if isinstance(retry, int) and not isinstance(retry, bool) and retry > 0:
            saved.body_retry_count = min(3, retry)
            saved.next_body_retry_at = now + timedelta(minutes=v.interval_minutes)
        if material.body_status == "ok" or retry == 0:
            saved.body_retry_count, saved.next_body_retry_at = 0, None
        saved.published_at, saved.source_updated_at = (
            material.published_at,
            material.source_updated_at,
        )
        saved.material_metadata = {
            **material.metadata,
            "content_format": material.content_format,
            "url": material.url,
            "categories": list(material.categories),
        }
        return AppliedEditorialMaterial(
            "succeeded",
            "created"
            if previous_version is None
            else "revised"
            if previous_version != ingested.content_version_id
            else "unchanged",
            ingested.content_id,
            ingested.content_version_id,
        )

    def review_run(
        self, *, owner_id: UUID, profile_id: UUID, run_id: UUID, command: EditorialRunReviewInput
    ) -> EditorialRunResult:
        self._session.rollback()
        with self._session.begin():
            return self.review_run_in_transaction(
                owner_id=owner_id, profile_id=profile_id, run_id=run_id, command=command
            )

    def review_run_in_transaction(
        self, *, owner_id: UUID, profile_id: UUID, run_id: UUID, command: EditorialRunReviewInput
    ) -> EditorialRunResult:
        if not self._session.in_transaction():
            raise RuntimeError("editorial operator writes require caller transaction")
        p = self._profile(owner_id, profile_id, lock=True)
        run = self._session.scalar(
            select(EditorialSourceRun)
            .where(
                EditorialSourceRun.owner_id == owner_id,
                EditorialSourceRun.profile_id == profile_id,
                EditorialSourceRun.id == run_id,
            )
            .with_for_update()
        )
        if run is None:
            raise ApplicationError("resource_not_found")
        digest = fingerprint(command.model_dump(mode="json")).hex()
        if run.review_audit is not None:
            if (
                run.review_audit.get("operation_id") == str(command.operation_id)
                and run.review_audit.get("hash") == digest
            ):
                return self._result(run)
            raise ApplicationError("idempotency_conflict")
        if (
            p.revision != command.expected_revision
            or (
                command.action == "acknowledge_unknown" and run.status not in {"unknown", "running"}
            )
            or (command.action == "retry_failed" and run.status not in {"failed", "blocked"})
        ):
            raise ApplicationError("editorial_version_conflict")
        now = self._clock()
        accept_audit_in_transaction(
            self._session,
            owner_id=owner_id,
            operation_id=command.operation_id,
            action="editorial_source.review",
            target_ref=f"editorial-source-run:{run.id}",
            reason=command.reason,
            payload=command.model_dump(mode="json"),
            now=now,
            before_state={"status": run.status, "revision": p.revision},
        )
        run.review_audit = {
            **command.model_dump(mode="json"),
            "hash": digest,
            "previous_status": run.status,
            "reviewed_at": self._clock().isoformat(),
        }
        run.status, run.prepared_page, run.updated_at = "cancelled", None, self._clock()
        p.revision += 1
        p.next_fetch_at, p.updated_at = (
            self._clock() + timedelta(minutes=self._version(p).interval_minutes),
            self._clock(),
        )
        result = self._result(run)
        complete_audit_in_transaction(
            self._session,
            owner_id=owner_id,
            operation_id=command.operation_id,
            after_state=result.model_dump(mode="json"),
            now=now,
        )
        return result

    def _failure_health(
        self,
        p: EditorialSourceProfile,
        v: EditorialSourceVersion,
        reason: str | None,
        now: datetime,
        *,
        unknown: bool,
    ) -> None:
        soft = reason in {
            "budget_exhausted",
            "source_authorization_required",
            "real_network_disabled",
            "cancelled",
            "rate_limited",
            "x_gap_pending",
            "mp_body_pending",
            "mp_receipt_window",
        }
        if not soft:
            p.failure_count += 1
            p.health = (
                "failing" if p.failure_count >= (3 if v.kind == "mp_account" else 5) else "degraded"
            )
        p.last_failure_code, p.updated_at = reason, now
        p.next_fetch_at = (
            None
            if unknown
            else now
            + timedelta(minutes=min(360, v.interval_minutes * (2 ** min(p.failure_count, 5))))
        )

    def _require_ready(
        self, p: EditorialSourceProfile, v: EditorialSourceVersion, now: datetime
    ) -> None:
        conn = self._session.scalar(
            select(SourceConnection)
            .where(SourceConnection.owner_id == p.owner_id, SourceConnection.id == v.connection_id)
            .with_for_update()
        )
        if conn is None or conn.status != "active":
            raise ApplicationError("connection_disabled")
        if conn.current_version != v.connection_version:
            raise ApplicationError("connection_version_conflict")
        SourceAccessPolicyService(
            self._session, clock=lambda: now
        ).require_admission_ready_in_transaction(
            owner_id=p.owner_id,
            source_key=p.source_key,
            capability=capability_for(v.kind),
            data_class=DataClass.STRUCTURED,
        )
        admission = SourceAccessPolicyService(
            self._session, clock=lambda: now
        ).admit_payload_in_transaction(
            owner_id=p.owner_id,
            source_key=p.source_key,
            capability=capability_for(v.kind),
            data_class=DataClass.STRUCTURED,
            collected_at=now,
            payload={"title": p.name},
        )
        if admission.policy_version != v.policy_version:
            raise ApplicationError("editorial_version_conflict")
        if v.configuration.get("rsshub") is not None:
            require_editorial_rsshub_execution_in_transaction(
                self._session,
                owner_id=p.owner_id,
                profile_id=p.id,
                configuration_version=v.version,
                revision=p.revision,
                now=now,
            )

    def require_run_admission(
        self, *, owner_id: UUID, run_id: UUID, guard: Guard | None = None
    ) -> None:
        """Recheck configuration, lease and policy immediately before each request."""
        self._session.rollback()
        with self._session.begin():
            run, profile, version = self._current_run(owner_id, run_id, guard)
            if run.status != "running":
                raise ApplicationError("editorial_version_conflict")
            self._require_ready(profile, version, self._clock())

    def _current_run(
        self, owner_id: UUID, run_id: UUID, guard: Guard | None
    ) -> tuple[EditorialSourceRun, EditorialSourceProfile, EditorialSourceVersion]:
        run = self._session.scalar(
            select(EditorialSourceRun)
            .where(EditorialSourceRun.owner_id == owner_id, EditorialSourceRun.id == run_id)
            .with_for_update()
        )
        if run is None:
            raise ApplicationError("resource_not_found")
        p = self._profile(owner_id, run.profile_id, lock=True)
        if (
            not p.enabled
            or p.current_version != run.configuration_version
            or p.revision != run.profile_revision
            or (guard is not None and not guard(self._session, owner_id, run.job_id))
        ):
            raise ApplicationError("editorial_version_conflict")
        return run, p, self._version(p)

    def _has_unresolved(self, p: EditorialSourceProfile) -> bool:
        return (
            self._session.scalar(
                select(EditorialSourceRun.id)
                .where(
                    EditorialSourceRun.owner_id == p.owner_id,
                    EditorialSourceRun.profile_id == p.id,
                    EditorialSourceRun.status.in_(("running", "staged", "unknown")),
                )
                .limit(1)
            )
            is not None
        )

    def _profile(
        self, owner_id: UUID, profile_id: UUID, *, lock: bool = False
    ) -> EditorialSourceProfile:
        query = select(EditorialSourceProfile).where(
            EditorialSourceProfile.owner_id == owner_id, EditorialSourceProfile.id == profile_id
        )
        p = self._session.scalar(query.with_for_update() if lock else query)
        if p is None:
            raise ApplicationError("resource_not_found")
        return p

    def _version(self, p: EditorialSourceProfile) -> EditorialSourceVersion:
        v = self._session.get(EditorialSourceVersion, (p.id, p.current_version))
        if v is None or v.owner_id != p.owner_id:
            raise ApplicationError("resource_not_found")
        return v

    def _view(self, p: EditorialSourceProfile) -> EditorialProfileView:
        v = self._version(p)
        return EditorialProfileView(
            id=p.id,
            source_key=p.source_key,
            name=p.name,
            enabled=p.enabled,
            revision=p.revision,
            configuration_version=v.version,
            configuration_sha256=fingerprint(v.configuration).hex(),
            configuration=v.configuration,
            participation_mode=v.participation_mode,
            tier=v.tier,
            first_party=v.first_party,
            connection_id=v.connection_id,
            connection_version=v.connection_version,
            policy_version=v.policy_version,
            interval_minutes=v.interval_minutes,
            health=p.health,
            failure_count=p.failure_count,
            last_fetch_at=p.last_fetch_at,
            last_ok_at=p.last_ok_at,
            next_fetch_at=p.next_fetch_at,
            has_backlog=bool(EditorialCursor.model_validate(p.cursor).x_backlog),
            has_unknown_run=self._has_unresolved(p),
        )

    @staticmethod
    def _result(r: EditorialSourceRun) -> EditorialRunResult:
        prepared = r.prepared_page or {}
        counts = cast(dict[str, object], prepared.get("_filter_receipt", prepared))
        return EditorialRunResult(
            run_id=r.id,
            status="running" if r.status == "staged" else r.status,
            configuration_version=r.configuration_version,
            found=r.found,
            filtered=cast(int, counts.get("filtered", 0)),
            created=r.created,
            revised=r.revised,
            reason=r.failure_code,
        )


def list_editorial_source_health_in_transaction(
    session: Session, *, owner_id: UUID, limit: int = 200, after_source_key: str | None = None
) -> tuple[EditorialSourceOperationalHealth, ...]:
    """Operational metadata only, with no configuration, tokens, body or source request."""
    if not session.in_transaction() or not 1 <= limit <= 200:
        raise ValueError("source health requires a bounded caller transaction")
    if after_source_key is not None and not 1 <= len(after_source_key) <= 64:
        raise ValueError("source health keyset is outside its bound")
    service = EditorialSourceService(session)
    query = select(EditorialSourceProfile).where(EditorialSourceProfile.owner_id == owner_id)
    if after_source_key is not None:
        query = query.where(EditorialSourceProfile.source_key > after_source_key)
    profiles = session.scalars(query.order_by(EditorialSourceProfile.source_key).limit(limit))
    return tuple(
        EditorialSourceOperationalHealth(
            id=p.id,
            source_key=p.source_key,
            name=p.name,
            kind=service._view(p).configuration.kind,
            enabled=p.enabled,
            created_at=p.created_at,
            health=p.health,
            consecutive_failures=p.failure_count,
            last_success_at=p.last_ok_at,
            last_error=p.last_failure_code,
        )
        for p in profiles
    )
