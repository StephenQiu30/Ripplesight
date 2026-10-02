"""Source-owned avatar cache admission; pixels belong to original Evidence lifecycle."""

from __future__ import annotations

import re
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import Literal, cast
from uuid import UUID, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from connections.editorial_icon_models import EditorialSourceIcon
from connections.editorial_models import (
    EditorialSourceMaterialReceipt,
    EditorialSourceProfile,
    EditorialSourceRun,
)
from connections.editorial_services import EditorialSourceService, capability_for
from core.errors import ApplicationError
from evidence.schemas import AdmittedSourcePayload, CleanupTargetKind, CleanupTargetSpec, DataClass
from evidence.services import (
    LifecycleService,
    RetentionPolicyUnavailableError,
    SourceAccessPolicyService,
    SourceAccessUnavailableError,
    load_readable_resources_in_transaction,
)
from jobs.schemas import JobAcceptanceInput, JobObservationContext, JobView
from jobs.services import JobService, load_job_execution_configuration
from operations.services import (
    accept_audit_in_transaction,
    complete_audit_in_transaction,
    load_completed_audit_in_transaction,
)
from sources.editorial_schemas import fingerprint, public_url
from sources.icons import BATCH, MP_RETRY_DAYS, RETRY_DAYS
from sources.icons_schemas import (
    SourceIconObjectRef,
    SourceIconRefreshInput,
    SourceIconSeed,
    SourceIconVariant,
    SourceIconView,
)

RESOURCE_TYPE = "source_icon"
_NAMESPACE = UUID("4b93724e-36de-4f52-8d58-14e55e04b66d")


def icon_media_admission_in_transaction(
    session: Session, *, seed: SourceIconSeed, url: str, at: datetime, now: datetime
) -> AdmittedSourcePayload:
    url = public_url(url)
    admitted = SourceAccessPolicyService(session, clock=lambda: now).admit_payload_in_transaction(
        owner_id=seed.owner_id,
        source_key=seed.source_key,
        capability=capability_for(seed.configuration.kind),
        data_class=DataClass.MEDIA,
        collected_at=at,
        payload={"url": url, "source_icon": "avatar"},
    )
    if (
        admitted.fields.get("url") != url
        or admitted.fields.get("source_icon") != "avatar"
        or admitted.policy_version != seed.policy_version
        or admitted.expires_at <= now
    ):
        raise ApplicationError("editorial_source_unavailable")
    return admitted


def _seed(session: Session, p: EditorialSourceProfile, *, scheduled: datetime) -> SourceIconSeed:
    service = EditorialSourceService(session, clock=lambda: scheduled)
    profile = service._view(p)
    if profile.connection_id is None or profile.connection_version is None:
        raise ApplicationError("editorial_source_unavailable")
    receipts = session.scalars(
        select(EditorialSourceMaterialReceipt)
        .join(EditorialSourceRun, EditorialSourceRun.id == EditorialSourceMaterialReceipt.run_id)
        .where(
            EditorialSourceMaterialReceipt.owner_id == p.owner_id,
            EditorialSourceMaterialReceipt.profile_id == p.id,
            EditorialSourceRun.configuration_version == profile.configuration_version,
        )
        .order_by(
            EditorialSourceMaterialReceipt.created_at.desc(),
            EditorialSourceMaterialReceipt.identity_key,
        )
        .limit(10)
    ).all()
    urls: list[str] = []
    avatar = None
    own_author = re.fullmatch(
        r"from:([A-Za-z0-9_]{1,15})(?:\s+-(?:filter:replies|is:reply))?",
        profile.configuration.query or "",
        re.IGNORECASE,
    )
    for receipt in receipts:
        url = receipt.material_metadata.get("url")
        if isinstance(url, str):
            with suppress(ValueError):
                urls.append(public_url(url))
        author = receipt.material_metadata.get("author_handle")
        candidate = receipt.material_metadata.get("avatar_url")
        if (
            avatar is None
            and own_author is not None
            and isinstance(author, str)
            and author.casefold() == own_author[1].casefold()
            and isinstance(candidate, str)
        ):
            with suppress(ValueError):
                avatar = public_url(candidate)
    return SourceIconSeed(
        owner_id=p.owner_id,
        profile_id=p.id,
        source_key=p.source_key,
        configuration_version=profile.configuration_version,
        profile_revision=profile.revision,
        policy_version=profile.policy_version,
        connection_id=profile.connection_id,
        connection_version=profile.connection_version,
        configuration=profile.configuration,
        article_urls=tuple(urls),
        avatar_url=avatar,
        scheduled_for_at=scheduled,
    )


def require_icon_seed_in_transaction(
    session: Session, *, seed: SourceIconSeed, now: datetime, job_id: UUID | None = None
) -> None:
    if not session.in_transaction():
        raise RuntimeError("icon admission requires caller transaction")
    service = EditorialSourceService(session, clock=lambda: now)
    p = service._profile(seed.owner_id, seed.profile_id, lock=True)
    profile = service._view(p)
    if (
        not p.enabled
        or p.source_key != seed.source_key
        or p.current_version != seed.configuration_version
        or p.revision != seed.profile_revision
        or profile.policy_version != seed.policy_version
        or profile.connection_id != seed.connection_id
        or profile.connection_version != seed.connection_version
        or fingerprint(profile.configuration.model_dump(mode="json"))
        != fingerprint(seed.configuration.model_dump(mode="json"))
    ):
        raise ApplicationError("editorial_version_conflict")
    service._require_ready(p, service._version(p), now)
    if job_id is not None:
        actual = load_job_execution_configuration(session, job_id=job_id)
        if (
            actual is None
            or actual.owner_id != seed.owner_id
            or actual.kind != "source.icons"
            or actual.observation.configuration_ref != f"source-icons:{seed.profile_id}"
            or actual.observation.configuration_version != seed.configuration_version
            or actual.observation.source_key != seed.source_key
            or actual.scope.get("source_icon") != seed.model_dump_json()
            or actual.scope.get("icon_input_hash") != seed.sha256
        ):
            raise ApplicationError("editorial_version_conflict")


def _accept_icon_job(
    session: Session, *, seed: SourceIconSeed, operation_id: UUID, now: datetime
) -> JobView:
    return JobService(session, clock=lambda: now).accept_in_transaction(
        owner_id=seed.owner_id,
        command=JobAcceptanceInput(
            operation_id=operation_id,
            kind="source.icons",
            observation=JobObservationContext(
                configuration_ref=f"source-icons:{seed.profile_id}",
                configuration_version=seed.configuration_version,
                source_key=seed.source_key,
                source_capability=capability_for(seed.configuration.kind),
            ),
            scheduled_for_at=seed.scheduled_for_at,
            scope={"source_icon": seed.model_dump_json(), "icon_input_hash": seed.sha256},
        ),
    )


def enqueue_due_source_icons_in_transaction(
    session: Session, now: datetime, *, enabled: bool, limit: int = BATCH
) -> int:
    if not session.in_transaction() or now.utcoffset() is None or not 1 <= limit <= BATCH:
        raise RuntimeError("icon scheduling needs aware bounded caller transaction")
    if not enabled:
        return 0
    count = 0
    for p in session.scalars(
        select(EditorialSourceProfile)
        .where(EditorialSourceProfile.enabled.is_(True))
        .order_by(EditorialSourceProfile.id)
        .limit(limit)
        .with_for_update()
    ):
        cached = session.get(EditorialSourceIcon, (p.owner_id, p.id))
        if cached and cached.status in {"running", "unknown"}:
            continue
        current_cache = cached and cached.configuration_version == p.current_version
        scheduled = (
            cached.next_retry_at
            if current_cache and cached and cached.next_retry_at
            else p.created_at
        )
        if scheduled > now:
            continue
        seed = _seed(session, p, scheduled=scheduled)
        if (
            current_cache
            and cached
            and cached.status == "ready"
            and (seed.configuration.kind != "x_search" or cached.source_url == seed.avatar_url)
        ):
            continue
        if seed.configuration.kind == "x_search" and seed.avatar_url is None:
            continue
        if seed.configuration.kind == "external" and not seed.article_urls:
            continue
        _accept_icon_job(session, seed=seed, operation_id=uuid5(_NAMESPACE, seed.sha256), now=now)
        count += 1
    return count


class SourceIconService:
    def __init__(
        self, session: Session, *, clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    ) -> None:
        self.session, self.clock = session, clock

    def refresh(
        self, *, owner_id: UUID, profile_id: UUID, command: SourceIconRefreshInput
    ) -> JobView:
        self.session.rollback()
        with self.session.begin():
            _audit, replayed = accept_audit_in_transaction(
                self.session,
                owner_id=owner_id,
                operation_id=command.operation_id,
                action="source_icon.refresh",
                target_ref=f"editorial-source:{profile_id}",
                reason=command.reason,
                payload=command.model_dump(mode="json"),
                now=self.clock(),
                before_state={"expected_revision": command.expected_revision},
            )
            if replayed:
                completed = load_completed_audit_in_transaction(
                    self.session,
                    owner_id=owner_id,
                    operation_id=command.operation_id,
                )
                if completed is not None:
                    return JobView.model_validate(completed)
            p = EditorialSourceService(self.session)._profile(owner_id, profile_id, lock=True)
            if p.revision != command.expected_revision:
                raise ApplicationError("editorial_version_conflict")
            cached = self.session.get(EditorialSourceIcon, (owner_id, profile_id))
            if cached and (
                cached.status == "running"
                or (cached.status == "unknown" and command.action != "retry_unknown")
            ):
                raise ApplicationError("editorial_version_conflict")
            seed = _seed(self.session, p, scheduled=self.clock())
            require_icon_seed_in_transaction(self.session, seed=seed, now=self.clock())
            accepted = _accept_icon_job(
                self.session, seed=seed, operation_id=command.operation_id, now=self.clock()
            )
            if cached and command.action == "retry_unknown":
                cached.status, cached.next_retry_at, cached.updated_at = (
                    "blocked",
                    self.clock(),
                    self.clock(),
                )
            complete_audit_in_transaction(
                self.session,
                owner_id=owner_id,
                operation_id=command.operation_id,
                after_state=accepted.model_dump(mode="json"),
                now=self.clock(),
            )
            return accepted

    def begin_in_transaction(
        self, *, seed: SourceIconSeed, job_id: UUID, operation_id: UUID
    ) -> bool:
        require_icon_seed_in_transaction(self.session, seed=seed, now=self.clock(), job_id=job_id)
        cached = self.session.get(
            EditorialSourceIcon, (seed.owner_id, seed.profile_id), with_for_update=True
        )
        if cached and cached.job_id == job_id:
            if cached.input_hash.hex() != seed.sha256:
                raise ApplicationError("idempotency_conflict")
            if cached.status == "running":
                cached.status, cached.failure_code, cached.updated_at = (
                    "unknown",
                    "icon_request_abandoned",
                    self.clock(),
                )
            return False
        if cached and cached.status in {"running", "unknown"}:
            raise ApplicationError("editorial_version_conflict")
        if cached is None:
            cached = EditorialSourceIcon(
                owner_id=seed.owner_id, profile_id=seed.profile_id, created_at=self.clock()
            )
            self.session.add(cached)
        cached.source_key, cached.configuration_version, cached.profile_revision = (
            seed.source_key,
            seed.configuration_version,
            seed.profile_revision,
        )
        cached.input_hash, cached.operation_id, cached.job_id = (
            bytes.fromhex(seed.sha256),
            operation_id,
            job_id,
        )
        cached.status, cached.failure_code, cached.media_refs = "running", None, []
        cached.source_url, cached.checked_at, cached.next_retry_at, cached.updated_at = (
            None,
            None,
            None,
            self.clock(),
        )
        self.session.flush()
        return True

    def _cache_in_transaction(self, *, seed: SourceIconSeed, job_id: UUID) -> EditorialSourceIcon:
        cached = self.session.get(
            EditorialSourceIcon, (seed.owner_id, seed.profile_id), with_for_update=True
        )
        if cached is None or cached.job_id != job_id or cached.input_hash.hex() != seed.sha256:
            raise ApplicationError("editorial_version_conflict")
        return cached

    def require_running_in_transaction(self, *, seed: SourceIconSeed, job_id: UUID) -> None:
        if self._cache_in_transaction(seed=seed, job_id=job_id).status != "running":
            raise ApplicationError("editorial_version_conflict")

    def stage_objects_in_transaction(
        self,
        *,
        seed: SourceIconSeed,
        job_id: UUID,
        url: str,
        objects: tuple[SourceIconObjectRef, ...],
    ) -> None:
        require_icon_seed_in_transaction(self.session, seed=seed, now=self.clock(), job_id=job_id)
        cached = self._cache_in_transaction(seed=seed, job_id=job_id)
        if cached.status != "running" or {r.mode for r in objects} != {"avatar-48", "avatar-96"}:
            raise ApplicationError("editorial_version_conflict")
        admission = icon_media_admission_in_transaction(
            self.session, seed=seed, url=url, at=self.clock(), now=self.clock()
        )
        evidence = LifecycleService(self.session, clock=self.clock).track_resource_in_transaction(
            owner_id=seed.owner_id,
            resource_type=RESOURCE_TYPE,
            resource_id=uuid5(job_id, f"source-icon:{url}"),
            admission=admission,
            cleanup_targets=[
                CleanupTargetSpec(kind=CleanupTargetKind.MINIO_OBJECT, reference=o.object_name)
                for o in objects
            ],
        )
        cached.media_refs = [
            o.model_copy(update={"evidence_resource_id": evidence.id}).model_dump(mode="json")
            for o in objects
        ]
        cached.source_url, cached.updated_at = url, self.clock()

    def finish_in_transaction(
        self,
        *,
        seed: SourceIconSeed,
        job_id: UUID,
        status: Literal["ready", "missing", "blocked", "unknown"],
        reason: str | None = None,
    ) -> None:
        cached = self._cache_in_transaction(seed=seed, job_id=job_id)
        if status == "ready":
            require_icon_seed_in_transaction(
                self.session, seed=seed, now=self.clock(), job_id=job_id
            )
            if (
                cached.status != "running"
                or len(cached.media_refs) != 2
                or cached.source_url is None
            ):
                raise ApplicationError("editorial_version_conflict")
            icon_media_admission_in_transaction(
                self.session, seed=seed, url=cached.source_url, at=self.clock(), now=self.clock()
            )
        cached.status, cached.failure_code, cached.checked_at, cached.updated_at = (
            status,
            reason,
            self.clock(),
            self.clock(),
        )
        cached.next_retry_at = (
            None
            if status in {"ready", "unknown"}
            else self.clock()
            + timedelta(
                days=MP_RETRY_DAYS if seed.configuration.kind == "mp_account" else RETRY_DAYS
            )
        )

    def read_in_transaction(self, *, owner_id: UUID, profile_id: UUID) -> SourceIconView:
        profile = EditorialSourceService(self.session)._view(
            EditorialSourceService(self.session)._profile(owner_id, profile_id)
        )
        cached = self.session.get(EditorialSourceIcon, (owner_id, profile_id))
        base = dict(
            profile_id=profile.id,
            configuration_version=profile.configuration_version,
            checked_at=cached.checked_at if cached else None,
            next_retry_at=cached.next_retry_at if cached else None,
        )
        if cached is None:
            return SourceIconView(**base, status="not_configured")
        if (
            cached.configuration_version != profile.configuration_version
            or cached.profile_revision != profile.revision
        ):
            return SourceIconView(**base, status="obsolete")
        if not profile.enabled:
            return SourceIconView(
                **base, status="blocked", failure_code="editorial_source_disabled"
            )
        status = cast(Literal["ready", "missing", "blocked", "unknown", "running"], cached.status)
        if status != "ready" or cached.source_url is None:
            return SourceIconView(**base, status=status, failure_code=cached.failure_code)
        try:
            return self._read_ready_in_transaction(
                owner_id=owner_id, profile_id=profile_id, cached=cached, base=base
            )
        except (ApplicationError, SourceAccessUnavailableError, RetentionPolicyUnavailableError):
            return SourceIconView(
                **base, status="blocked", failure_code="editorial_source_unavailable"
            )

    def _read_ready_in_transaction(
        self,
        *,
        owner_id: UUID,
        profile_id: UUID,
        cached: EditorialSourceIcon,
        base: dict[str, object],
    ) -> SourceIconView:
        if cached.source_url is None:
            return SourceIconView(**base, status="blocked")
        seed = _seed(
            self.session,
            EditorialSourceService(self.session)._profile(owner_id, profile_id),
            scheduled=cached.created_at,
        )
        require_icon_seed_in_transaction(self.session, seed=seed, now=self.clock())
        admission = icon_media_admission_in_transaction(
            self.session,
            seed=seed,
            url=cached.source_url,
            at=cached.checked_at or cached.created_at,
            now=self.clock(),
        )
        resource_id = uuid5(cached.job_id, f"source-icon:{cached.source_url}")
        live = load_readable_resources_in_transaction(
            self.session,
            owner_id=owner_id,
            resource_type=RESOURCE_TYPE,
            resource_ids={resource_id},
            now=self.clock(),
        ).get(resource_id)
        if (
            live is None
            or live.source_policy_id != admission.policy_id
            or live.source_policy_version != admission.policy_version
            or live.retention_policy_id != admission.retention_policy_id
            or live.retention_policy_version != admission.retention_policy_version
        ):
            return SourceIconView(
                **base, status="blocked", failure_code="editorial_source_unavailable"
            )
        objects = tuple(SourceIconObjectRef.model_validate(r) for r in cached.media_refs)
        if any(o.evidence_resource_id != live.id for o in objects):
            raise ApplicationError("editorial_version_conflict")
        return SourceIconView(
            **base,
            status="ready",
            variants=tuple(
                SourceIconVariant(
                    mode=o.mode,
                    url=f"/api/editorial-sources/{profile_id}/icon/{o.mode}",
                    sha256=o.sha256,
                    mime_type=o.mime_type,
                    width=o.width,
                    height=o.height,
                )
                for o in objects
            ),
        )

    def get(self, *, owner_id: UUID, profile_id: UUID) -> SourceIconView:
        self.session.rollback()
        with self.session.begin():
            return self.read_in_transaction(owner_id=owner_id, profile_id=profile_id)

    def read_object_in_transaction(
        self, *, owner_id: UUID, profile_id: UUID, mode: Literal["avatar-48", "avatar-96"]
    ) -> SourceIconObjectRef | None:
        view = self.read_in_transaction(owner_id=owner_id, profile_id=profile_id)
        if view.status != "ready":
            return None
        cached = self.session.get(EditorialSourceIcon, (owner_id, profile_id))
        if cached is None:
            return None
        for raw in cached.media_refs:
            item = SourceIconObjectRef.model_validate(raw)
            if item.mode == mode:
                return item
        return None

    def profile_id_by_source_key_in_transaction(
        self, *, owner_id: UUID, source_key: str
    ) -> UUID | None:
        return self.session.scalar(
            select(EditorialSourceProfile.id).where(
                EditorialSourceProfile.owner_id == owner_id,
                EditorialSourceProfile.source_key == source_key,
            )
        )

    def get_by_source_key(self, *, owner_id: UUID, source_key: str) -> SourceIconView | None:
        self.session.rollback()
        with self.session.begin():
            profile_id = self.profile_id_by_source_key_in_transaction(
                owner_id=owner_id, source_key=source_key
            )
            if profile_id is None:
                return None
            return self.read_in_transaction(owner_id=owner_id, profile_id=profile_id)


def read_source_icon_urls_in_transaction(
    session: Session, *, owner_id: UUID, source_keys: tuple[str, ...], now: datetime
) -> dict[str, str]:
    """Project only source-owned current MEDIA/Evidence-readable avatar URLs in caller TX."""
    if not session.in_transaction() or now.utcoffset() is None or len(source_keys) > 100:
        raise ValueError("source avatar projection requires a bounded aware caller transaction")
    service = SourceIconService(session, clock=lambda: now)
    rows = session.execute(
        select(EditorialSourceProfile.source_key, EditorialSourceProfile.id).where(
            EditorialSourceProfile.owner_id == owner_id,
            EditorialSourceProfile.source_key.in_(set(source_keys)),
        )
    )
    result = {}
    for key, profile_id in rows:
        view = service.read_in_transaction(owner_id=owner_id, profile_id=profile_id)
        if view.status == "ready" and any(v.mode == "avatar-48" for v in view.variants):
            result[key] = f"/api/site/source-icons/{key}/avatar-48"
    return result
