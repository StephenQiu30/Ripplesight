"""Durable media fetch, guarded Evidence ownership, MinIO preparation, and explicit recovery."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime
from functools import partial
from typing import Any, Literal, Protocol, cast
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from evidence.schemas import (
    CleanupTargetKind,
    CleanupTargetSpec,
    ProvenanceManifestInput,
    ProvenanceResourceRef,
)
from evidence.services import (
    LifecycleService,
    ProvenanceService,
    load_readable_resources_in_transaction,
)
from jobs.execution import ExecutionLease, JobCompletion, JobExecutionFailure, JobExecutionService
from jobs.schemas import JobFailureCategory, JobMessage, JobStatus
from jobs.services import load_job_execution_configuration
from publication.media_mirror_codec import encode_image_renditions
from publication.media_mirror_fetch import MediaMirrorClient, Resolver, resolve_public_addresses
from publication.media_mirror_meter import MediaRequestMeter
from publication.media_mirror_models import PublicationMediaFile, PublicationMediaRun
from publication.media_mirror_services import (
    CONFIGURATION_REF,
    RESOURCE_TYPE,
    media_admission_in_transaction,
    require_media_grant_in_transaction,
    require_media_run_source_in_transaction,
    source_material_in_transaction,
)
from publication.schemas import FrozenPublicationReference


class MediaObjectStorage(Protocol):
    def check_bucket(self) -> None: ...
    def put(self, name: str, body: bytes, mime_type: str) -> None: ...
    def get(self, name: str, *, max_bytes: int) -> bytes: ...


class PublicationMediaExecutor:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        storage: MediaObjectStorage,
        *,
        allow_external_requests: bool = False,
        image_max_bytes: int = 15 * 1024 * 1024,
        video_max_bytes: int = 64 * 1024 * 1024,
        redirect_hosts: frozenset[str] = frozenset(),
        clock: Callable[[], datetime] | None = None,
        transport: httpx.BaseTransport | None = None,
        resolver: Resolver = resolve_public_addresses,
        lease_seconds: int = 30,
    ) -> None:
        self.sessions, self.storage = sessions, storage
        self.allowed, self.image_cap, self.video_cap = (
            allow_external_requests,
            image_max_bytes,
            video_max_bytes,
        )
        self.redirect_hosts, self.clock = redirect_hosts, clock or (lambda: datetime.now(UTC))
        self.transport, self.resolver, self.lease_seconds = transport, resolver, lease_seconds

    def _execution(self, session: Session) -> JobExecutionService:
        return JobExecutionService(session, clock=self.clock, lease_seconds=self.lease_seconds)

    def _failure(
        self, code: str, *, category: JobFailureCategory = JobFailureCategory.INVALID_RESPONSE
    ) -> JobExecutionFailure:
        return JobExecutionFailure(
            error_code=code,
            category=category,
            occurred_at=self.clock(),
            next_action="复核固定正文、媒体许可与请求回执, unknown不自动重新下载",
            manual_retry_allowed=False,
        )

    def _run(self, session: Session, owner: UUID, run_id: UUID) -> PublicationMediaRun:
        run = session.get(PublicationMediaRun, (owner, run_id))
        if run is None:
            raise self._failure("media_run_unavailable", category=JobFailureCategory.INVALID_INPUT)
        return run

    def _guard(self, session: Session, *, owner: UUID, run_id: UUID) -> PublicationMediaRun:
        run = self._run(session, owner, run_id)
        require_media_run_source_in_transaction(session, run, now=self.clock())
        reference, candidates, _ = require_media_grant_in_transaction(
            session,
            owner_id=owner,
            content_id=run.content_id,
            version_id=run.content_version_id,
            policy_revision=run.policy_revision,
            now=self.clock(),
            fixed=FrozenPublicationReference.model_validate(run.fixed_reference),
            expected_body_sha256=run.fixed_reference.get("media_body_sha256"),
        )
        source_key, _ = source_material_in_transaction(
            session, owner_id=owner, reference=reference, now=self.clock()
        )
        if source_key != run.source_key:
            raise self._failure("media_source_changed", category=JobFailureCategory.INVALID_INPUT)
        for candidate in candidates:
            media_admission_in_transaction(
                session,
                owner_id=owner,
                source_key=source_key,
                url=candidate.original_url,
                at=run.created_at,
                now=self.clock(),
            )
        return run

    def _provenance(
        self, session: Session, run: PublicationMediaRun, file: PublicationMediaFile
    ) -> None:
        _, observation_id = source_material_in_transaction(
            session,
            owner_id=run.owner_id,
            reference=FrozenPublicationReference.model_validate(run.fixed_reference),
            now=self.clock(),
        )
        reference = load_readable_resources_in_transaction(
            session,
            owner_id=run.owner_id,
            resource_type="content_observation",
            resource_ids={observation_id},
            now=self.clock(),
        ).get(observation_id)
        subject = load_readable_resources_in_transaction(
            session,
            owner_id=run.owner_id,
            resource_type=RESOURCE_TYPE,
            resource_ids={file.id},
            now=self.clock(),
        ).get(file.id)
        if reference is None or subject is None:
            raise ValueError("media provenance material is unavailable")
        ProvenanceService(session, clock=self.clock).create_in_transaction(
            owner_id=run.owner_id,
            command=ProvenanceManifestInput(
                job_id=run.job_id,
                result_kind=f"media:{file.id.hex}",
                method_key="publication.media-mirror",
                method_version="1",
                method_parameters={
                    "policy_revision": run.policy_revision,
                    "sha256": file.content_sha256,
                    "format": file.mime_type,
                },
                subjects=(
                    ProvenanceResourceRef(
                        resource_record_id=subject.id, snapshot_ref=f"media:{file.id.hex}"
                    ),
                ),
                references=(
                    ProvenanceResourceRef(
                        resource_record_id=reference.id,
                        snapshot_ref=f"content-version:{run.content_version_id.hex}",
                    ),
                ),
            ),
        )

    def _recover_file(self, meter: MediaRequestMeter, run_id: UUID, file_id: UUID) -> None:
        meter.recover(file_id)
        with self.sessions.begin() as session:
            self._execution(session).require_current_lease_in_transaction(meter.lease)
            run = self._guard(session, owner=meter.message.owner_id, run_id=run_id)
            file = session.get(PublicationMediaFile, (run.owner_id, file_id))
            assert file
            if file.status != "running":
                return
            descriptors = dict(file.renditions)
        recovered = bool(descriptors)
        try:
            for spec in descriptors.values():
                body = self.storage.get(spec["object_name"], max_bytes=int(spec["byte_count"]))
                if (
                    len(body) != spec["byte_count"]
                    or hashlib.sha256(body).hexdigest() != spec["sha256"]
                ):
                    recovered = False
                    break
        except Exception:
            recovered = False
        with self.sessions.begin() as session:
            self._execution(session).require_current_lease_in_transaction(meter.lease)
            run = self._guard(session, owner=meter.message.owner_id, run_id=run_id)
            file = session.get(PublicationMediaFile, (run.owner_id, file_id))
            assert file
            if file.status != "running":
                return
            if recovered:
                self._provenance(session, run, file)
                file.status, file.reason = "complete", None
            else:
                file.status, file.reason = "unknown", "interrupted_request_or_object_write"
            file.updated_at = self.clock()

    def execute(
        self,
        message: JobMessage,
        lease: ExecutionLease,
        *,
        cancelled: Callable[[], bool] = lambda: False,
    ) -> JobCompletion | None:
        if message.kind != "publication.media_mirror":
            raise ValueError("wrong media Job kind")
        with self.sessions.begin() as session:
            configuration = load_job_execution_configuration(session, job_id=message.job_id)
            if (
                configuration is None
                or configuration.owner_id != message.owner_id
                or configuration.operation_id != message.operation_id
                or configuration.observation.configuration_ref != CONFIGURATION_REF
                or configuration.observation.configuration_version != 1
            ):
                raise self._failure("media_job_mismatch", category=JobFailureCategory.INVALID_INPUT)
            try:
                run_id = UUID(str(configuration.scope["media_run_id"]))
            except (ValueError, KeyError) as error:
                raise self._failure(
                    "media_job_mismatch", category=JobFailureCategory.INVALID_INPUT
                ) from error
            self._execution(session).require_current_lease_allowing_cancel_in_transaction(lease)
            run = self._run(session, message.owner_id, run_id)
            if run.job_id != message.job_id or run.operation_id != message.operation_id:
                raise self._failure("media_job_mismatch", category=JobFailureCategory.INVALID_INPUT)
            if run.status == "complete":
                return JobCompletion(status=JobStatus.SUCCEEDED)
            if run.status in {"partial", "unknown", "failed", "stale"}:
                raise self._failure("media_run_requires_review")
            if run.status == "cancelled":
                return None
            source_key = run.source_key
        if not self.allowed:
            raise self._failure(
                "media_external_requests_disabled", category=JobFailureCategory.PERMISSION_DENIED
            )
        meter = MediaRequestMeter(
            self.sessions,
            message,
            lease,
            clock=self.clock,
            source_key=source_key,
            lease_seconds=self.lease_seconds,
            guard=lambda session: self._guard(session, owner=message.owner_id, run_id=run_id),
        )
        meter.start()
        try:
            with self.sessions.begin() as session:
                self._execution(session).require_current_lease_allowing_cancel_in_transaction(
                    meter.lease
                )
                run = self._guard(session, owner=message.owner_id, run_id=run_id)
                run.status, run.updated_at = "running", self.clock()
                files = list(
                    session.scalars(
                        select(PublicationMediaFile)
                        .where(
                            PublicationMediaFile.owner_id == message.owner_id,
                            PublicationMediaFile.run_id == run_id,
                        )
                        .order_by(PublicationMediaFile.id)
                    )
                )
                ids = [(file.id, file.status) for file in files]
            for file_id, status in ids:
                if cancelled() or meter.broken.is_set():
                    with self.sessions.begin() as session:
                        self._execution(
                            session
                        ).require_current_lease_allowing_cancel_in_transaction(meter.lease)
                        run = self._run(session, message.owner_id, run_id)
                        run.status, run.reason, run.updated_at = (
                            "cancelled",
                            "job_cancelled",
                            self.clock(),
                        )
                        for file in session.scalars(
                            select(PublicationMediaFile).where(
                                PublicationMediaFile.owner_id == message.owner_id,
                                PublicationMediaFile.run_id == run_id,
                                PublicationMediaFile.status == "pending",
                            )
                        ):
                            file.status, file.updated_at = "cancelled", self.clock()
                    return None
                if status == "running":
                    self._recover_file(meter, run_id, file_id)
                    continue
                if status != "pending":
                    continue
                with self.sessions.begin() as session:
                    self._execution(session).require_current_lease_in_transaction(meter.lease)
                    run = self._guard(session, owner=message.owner_id, run_id=run_id)
                    file = cast(
                        PublicationMediaFile,
                        session.get(PublicationMediaFile, (message.owner_id, file_id)),
                    )
                    assert file
                    file.status, file.updated_at = "running", self.clock()
                    url, kind = file.source_url, cast(Literal["image", "video"], file.kind)
                client = MediaMirrorClient(
                    enabled=self.allowed,
                    before_request=partial(meter.before, file_id, "http"),
                    after_request=partial(meter.after, file_id, "http"),
                    cancelled=lambda: cancelled() or meter.broken.is_set(),
                    resolver=self.resolver,
                    transport=self.transport,
                    image_max_bytes=self.image_cap,
                    video_max_bytes=self.video_cap,
                    redirect_hosts=self.redirect_hosts,
                )
                try:
                    fetched = client.fetch(url, kind=kind)
                    encoded = encode_image_renditions(fetched.body) if kind == "image" else ()
                    objects: dict[str, tuple[bytes, dict[str, Any]]] = {}
                    values = [
                        (
                            "original",
                            fetched.body,
                            fetched.mime_type,
                            fetched.width,
                            fetched.height,
                            encoded[0].frame_count if encoded else 1,
                        )
                    ] + [
                        (
                            item.mode,
                            item.body,
                            item.mime_type,
                            item.width,
                            item.height,
                            item.frame_count,
                        )
                        for item in encoded
                    ]
                    for mode, body, mime, width, height, frames in values:
                        digest = hashlib.sha256(body).hexdigest()
                        name = f"media/{message.owner_id}/{file_id}/{mode}-{digest}"
                        objects[mode] = (
                            body,
                            {
                                "object_name": name,
                                "sha256": digest,
                                "mime_type": mime,
                                "byte_count": len(body),
                                "width": width,
                                "height": height,
                                "frame_count": frames,
                            },
                        )
                    with self.sessions.begin() as session:
                        self._execution(session).require_current_lease_in_transaction(meter.lease)
                        run = self._guard(session, owner=message.owner_id, run_id=run_id)
                        file = cast(
                            PublicationMediaFile,
                            session.get(PublicationMediaFile, (message.owner_id, file_id)),
                        )
                        assert file
                        admission = media_admission_in_transaction(
                            session,
                            owner_id=message.owner_id,
                            source_key=run.source_key,
                            url=url,
                            at=run.created_at,
                            now=self.clock(),
                        )
                        evidence = LifecycleService(
                            session, clock=self.clock
                        ).track_resource_in_transaction(
                            owner_id=message.owner_id,
                            resource_type=RESOURCE_TYPE,
                            resource_id=file_id,
                            admission=admission,
                            cleanup_targets=[
                                CleanupTargetSpec(
                                    kind=CleanupTargetKind.MINIO_OBJECT,
                                    reference=spec["object_name"],
                                )
                                for _, spec in objects.values()
                            ],
                        )
                        file.evidence_resource_id = evidence.id
                        file.content_sha256, file.byte_count, file.mime_type = (
                            hashlib.sha256(fetched.body).hexdigest(),
                            len(fetched.body),
                            fetched.mime_type,
                        )
                        file.renditions = {mode: spec for mode, (_, spec) in objects.items()}
                    if not meter.before(file_id, "put", 1):
                        raise PermissionError("bucket verification budget or lease denied")
                    checked: Literal["succeeded", "failed", "unknown"] = "unknown"
                    try:
                        self.storage.check_bucket()
                        checked = "succeeded"
                    except ValueError:
                        checked = "failed"
                        raise
                    finally:
                        meter.after(file_id, "put", 1, checked)
                    for index, (body, spec) in enumerate(objects.values(), 2):
                        if not meter.before(file_id, "put", index):
                            raise PermissionError("object write budget or lease denied")
                        outcome: Literal["succeeded", "unknown"] = "unknown"
                        try:
                            self.storage.put(spec["object_name"], body, spec["mime_type"])
                            outcome = "succeeded"
                        finally:
                            meter.after(file_id, "put", index, outcome)
                    with self.sessions.begin() as session:
                        self._execution(session).require_current_lease_in_transaction(meter.lease)
                        run = self._guard(session, owner=message.owner_id, run_id=run_id)
                        file = cast(
                            PublicationMediaFile,
                            session.get(PublicationMediaFile, (message.owner_id, file_id)),
                        )
                        assert file
                        self._provenance(session, run, file)
                        file.status, file.reason, file.updated_at = "complete", None, self.clock()
                except Exception as error:
                    # Missing local bytes never cause a completed remote request to be reissued.
                    with self.sessions.begin() as session:
                        self._execution(
                            session
                        ).require_current_lease_allowing_cancel_in_transaction(meter.lease)
                        file = cast(
                            PublicationMediaFile,
                            session.get(PublicationMediaFile, (message.owner_id, file_id)),
                        )
                        assert file
                        file.status = (
                            "unknown"
                            if isinstance(
                                error, (httpx.TransportError, TimeoutError, PermissionError)
                            )
                            or bool(file.renditions)
                            else "failed"
                        )
                        file.reason = (
                            "media_request_or_storage_unknown"
                            if file.status == "unknown"
                            else "media_invalid_or_unavailable"
                        )
                        file.updated_at = self.clock()
                finally:
                    client.close()
            # Cancellation can arrive inside the final response or final object write.
            # Record the domain result and let the shared Worker acknowledge cancellation.
            if cancelled():
                with self.sessions.begin() as session:
                    self._execution(session).require_current_lease_allowing_cancel_in_transaction(
                        meter.lease
                    )
                    run = self._run(session, message.owner_id, run_id)
                    run.status, run.reason, run.updated_at = (
                        "cancelled",
                        "job_cancelled",
                        self.clock(),
                    )
                    for file in session.scalars(
                        select(PublicationMediaFile).where(
                            PublicationMediaFile.owner_id == message.owner_id,
                            PublicationMediaFile.run_id == run_id,
                            PublicationMediaFile.status != "complete",
                        )
                    ):
                        file.status, file.reason, file.updated_at = (
                            "cancelled",
                            "job_cancelled",
                            self.clock(),
                        )
                return None
            with self.sessions.begin() as session:
                self._execution(session).require_current_lease_allowing_cancel_in_transaction(
                    meter.lease
                )
                run = self._guard(session, owner=message.owner_id, run_id=run_id)
                states = list(
                    session.scalars(
                        select(PublicationMediaFile.status).where(
                            PublicationMediaFile.owner_id == message.owner_id,
                            PublicationMediaFile.run_id == run_id,
                        )
                    )
                )
                complete = all(state == "complete" for state in states)
                run.status = (
                    "complete"
                    if complete
                    else "partial"
                    if "complete" in states
                    else "unknown"
                    if "unknown" in states
                    else "failed"
                )
                run.reason, run.updated_at = (
                    None if complete else "media_incomplete_requires_review",
                    self.clock(),
                )
            if complete:
                return JobCompletion(status=JobStatus.SUCCEEDED)
            if "complete" in states:
                return JobCompletion(
                    status=JobStatus.PARTIALLY_SUCCEEDED,
                    failure=self._failure("media_incomplete_requires_review"),
                )
            raise self._failure("media_incomplete_requires_review")
        finally:
            meter.close()
