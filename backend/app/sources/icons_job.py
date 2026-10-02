"""Source icon Worker: DNS-pinned discovery, original budgets, Evidence and object storage."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal, Protocol, cast
from uuid import UUID, uuid5

import httpx
from pydantic import ValidationError
from sqlalchemy.orm import Session, sessionmaker

from connections.editorial_icon_services import (
    SourceIconService,
    icon_media_admission_in_transaction,
    require_icon_seed_in_transaction,
)
from core.config import Settings
from core.errors import ApplicationError
from evidence.adapters.media_storage import create_media_storage
from evidence.services import RetentionPolicyUnavailableError, SourceAccessUnavailableError
from jobs.editorial_budgets import recover_source_icon_attempts_in_transaction
from jobs.execution import (
    ExecutionLease,
    JobCompletion,
    JobExecutionError,
    JobExecutionFailure,
    JobExecutionService,
)
from jobs.schemas import JobFailureCategory, JobMessage, JobStatus
from jobs.services import ResourceBudgetError, load_job_execution_configuration
from publication.media_mirror_codec import encode_avatar_renditions
from publication.media_mirror_fetch import MediaMirrorClient, Resolver, resolve_public_addresses
from publication.media_mirror_meter import MediaRequestMeter
from sources.icons import MAX_ICON_CANDIDATES, MP_PAUSE_SECONDS, home_of, icon_candidates, mp_avatar
from sources.icons_schemas import SourceIconObjectRef, SourceIconSeed


class SourceIconObjectStorage(Protocol):
    def check_bucket(self) -> None: ...
    def put(self, name: str, body: bytes, mime_type: str) -> None: ...
    def get(self, name: str, *, max_bytes: int) -> bytes: ...


class SourceIconJobExecutor:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        settings: Settings,
        *,
        lease_seconds: int = 30,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        storage: SourceIconObjectStorage | None = None,
        transport: httpx.BaseTransport | None = None,
        resolver: Resolver = resolve_public_addresses,
    ) -> None:
        self.sessions, self.settings, self.lease_seconds, self.clock = (
            sessions,
            settings,
            lease_seconds,
            clock,
        )
        self.storage, self.transport, self.resolver = storage, transport, resolver

    def _failure(self, code: str) -> JobExecutionFailure:
        return JobExecutionFailure(
            error_code=code,
            category=JobFailureCategory.INVALID_INPUT,
            occurred_at=self.clock(),
            next_action=(
                "核对当前来源版本、独立来源图标MEDIA用途与保留许可、网络预算和存储; "
                "未知请求须人工核验"
            ),
            manual_retry_allowed=False,
        )

    def execute(
        self,
        message: JobMessage,
        lease: ExecutionLease,
        *,
        cancelled: Callable[[], bool] | None = None,
    ) -> JobCompletion | None:
        if message.kind != "source.icons":
            raise ValueError("another Job kind reached source icons executor")
        if cancelled is not None and cancelled():
            return None
        deadline = time.monotonic() + 480

        def stopped() -> bool:
            return time.monotonic() >= deadline or (cancelled is not None and cancelled())

        def execution(session: Session) -> JobExecutionService:
            return JobExecutionService(session, lease_seconds=self.lease_seconds, clock=self.clock)

        with self.sessions.begin() as session:
            execution(session).require_current_operation_in_transaction(
                lease, owner_id=message.owner_id, operation_id=message.operation_id
            )
            actual = load_job_execution_configuration(session, job_id=message.job_id)
            raw_seed = actual.scope.get("source_icon") if actual else None
            if not isinstance(raw_seed, str):
                raise self._failure("invalid_editorial_input")
            try:
                seed = SourceIconSeed.model_validate_json(raw_seed)
            except (KeyError, ValidationError, TypeError) as error:
                raise self._failure("invalid_editorial_input") from error
            if (
                actual is None
                or seed is None
                or actual.owner_id != message.owner_id
                or actual.operation_id != message.operation_id
                or actual.kind != message.kind
                or actual.observation.configuration_ref != message.configuration_ref
                or actual.observation.configuration_version != message.configuration_version
                or actual.observation.source_key != message.source_key
                or actual.observation.source_capability != message.source_capability
            ):
                raise self._failure("editorial_version_conflict")
            recover_source_icon_attempts_in_transaction(
                session,
                owner_id=message.owner_id,
                operation_id=message.operation_id,
                now=self.clock(),
            )
            service = SourceIconService(session, clock=self.clock)
            try:
                ready = service.begin_in_transaction(
                    seed=seed, job_id=message.job_id, operation_id=message.operation_id
                )
            except (
                ApplicationError,
                SourceAccessUnavailableError,
                RetentionPolicyUnavailableError,
            ):
                return JobCompletion(
                    status=JobStatus.PARTIALLY_SUCCEEDED,
                    failure=self._failure("source_icon_admission_changed"),
                )
            if not ready:
                view = service.read_in_transaction(
                    owner_id=seed.owner_id, profile_id=seed.profile_id
                )
                return (
                    JobCompletion(status=JobStatus.SUCCEEDED)
                    if view.status in {"ready", "missing"}
                    else JobCompletion(
                        status=JobStatus.PARTIALLY_SUCCEEDED,
                        failure=self._failure("source_icon_result_unknown"),
                    )
                )
        owned_storage = create_media_storage(self.settings) if self.storage is None else None
        storage = self.storage or owned_storage
        if (
            not self.settings.source_icons_enabled
            or not self.settings.source_icons_external_requests_enabled
            or storage is None
        ):
            with self.sessions.begin() as session:
                execution(session).require_current_lease_in_transaction(lease)
                SourceIconService(session, clock=self.clock).finish_in_transaction(
                    seed=seed,
                    job_id=message.job_id,
                    status="blocked",
                    reason="source_icon_runtime_disabled",
                )
            if owned_storage is not None:
                owned_storage.close()
            return JobCompletion(
                status=JobStatus.PARTIALLY_SUCCEEDED,
                failure=self._failure("source_icon_runtime_disabled"),
            )
        current_url: str | None = None

        def guard(session: Session) -> None:
            if stopped():
                raise PermissionError("source icon cancellation or deadline")
            require_icon_seed_in_transaction(
                session, seed=seed, now=self.clock(), job_id=message.job_id
            )
            SourceIconService(session, clock=self.clock).require_running_in_transaction(
                seed=seed, job_id=message.job_id
            )
            if current_url is not None:
                icon_media_admission_in_transaction(
                    session, seed=seed, url=current_url, at=self.clock(), now=self.clock()
                )

        meter = MediaRequestMeter(
            self.sessions,
            message,
            lease,
            clock=self.clock,
            source_key=seed.source_key,
            lease_seconds=self.lease_seconds,
            guard=guard,
            component_key="source.icons",
            budget_job_ref=str(message.job_id),
            stage_prefix="source.icons",
        )
        clients: list[MediaMirrorClient] = []

        def client(identity: UUID) -> MediaMirrorClient:
            value = MediaMirrorClient(
                enabled=True,
                before_request=lambda i: meter.before(identity, "http", i),
                after_request=lambda i, outcome: meter.after(identity, "http", i, outcome),
                cancelled=stopped,
                resolver=self.resolver,
                transport=self.transport,
                redirect_hosts=frozenset(seed.configuration.allowed_hosts),
            )
            clients.append(value)
            return value

        def document(url: str, cap: int) -> tuple[str, str]:
            nonlocal current_url
            current_url = url
            found = client(uuid5(message.job_id, f"document:{url}")).fetch_document(
                url, max_bytes=cap
            )
            return found.body.decode("utf-8", errors="strict"), found.final_url

        objects_staged = False
        candidates: tuple[str, ...] = ()
        status: Literal["ready", "missing", "blocked", "unknown"] = "missing"
        reason: str | None = "source_icon_not_found"
        try:
            if seed.configuration.kind == "x_search":
                candidates = (seed.avatar_url,) if seed.avatar_url else ()
            elif seed.configuration.kind == "mp_account":
                for url in seed.article_urls[:2]:
                    pause_until = time.monotonic() + MP_PAUSE_SECONDS
                    while time.monotonic() < pause_until:
                        if stopped():
                            raise PermissionError("source icon cancelled")
                        time.sleep(min(0.1, pause_until - time.monotonic()))
                    try:
                        body, _final = document(url, 10_000_000)
                        avatar = mp_avatar(body)
                        if avatar:
                            candidates = (avatar,)
                            break
                    except (httpx.HTTPStatusError, ValueError, UnicodeError):
                        continue
            else:
                home = home_of(seed.article_urls, seed.configuration.model_dump(mode="json"))
                if home:
                    try:
                        body, final = document(home, 4_000_000)
                        candidates = icon_candidates(body, final)
                    except (httpx.HTTPStatusError, ValueError, UnicodeError):
                        candidates = (home + "/favicon.ico",)
            for url in candidates[:MAX_ICON_CANDIDATES]:
                if stopped():
                    raise PermissionError("source icon cancelled")
                current_url = url
                image_id = uuid5(message.job_id, f"image:{url}")
                try:
                    image = client(image_id).fetch(url, kind="image")
                    rendered = encode_avatar_renditions(image.body)
                except (httpx.HTTPStatusError, ValueError):
                    continue
                objects = tuple(
                    SourceIconObjectRef(
                        mode=cast(Literal["avatar-48", "avatar-96"], rendition.mode),
                        object_name=f"media/source-icons/{seed.owner_id}/{seed.profile_id}/{message.job_id}/{hashlib.sha256(rendition.body).hexdigest()}-{rendition.mode}",
                        evidence_resource_id=UUID(int=0),
                        sha256=hashlib.sha256(rendition.body).hexdigest(),
                        mime_type=cast(
                            Literal["image/webp", "image/jpeg", "image/svg+xml"],
                            rendition.mime_type,
                        ),
                        width=cast(Literal[48, 96], rendition.width),
                        height=cast(Literal[48, 96], rendition.height),
                        byte_count=len(rendition.body),
                    )
                    for rendition in rendered
                )
                with self.sessions.begin() as session:
                    execution(session).require_current_lease_in_transaction(meter.lease)
                    guard(session)
                    SourceIconService(session, clock=self.clock).stage_objects_in_transaction(
                        seed=seed, job_id=message.job_id, url=url, objects=objects
                    )
                objects_staged = True
                if not meter.before(image_id, "put", 1):
                    raise PermissionError("source icon bucket check denied")
                outcome: Literal["succeeded", "failed", "unknown"] = "unknown"
                try:
                    storage.check_bucket()
                    outcome = "succeeded"
                except ValueError:
                    outcome = "failed"
                    raise
                finally:
                    meter.after(image_id, "put", 1, outcome)
                for index, (rendition, ref) in enumerate(zip(rendered, objects, strict=True), 2):
                    if not meter.before(image_id, "put", index):
                        raise PermissionError("source icon object write denied")
                    outcome = "unknown"
                    try:
                        storage.put(ref.object_name, rendition.body, ref.mime_type)
                        outcome = "succeeded"
                    finally:
                        meter.after(image_id, "put", index, outcome)
                status, reason = "ready", None
                break
        except (httpx.TransportError, TimeoutError, OSError):
            status, reason = "unknown", "source_icon_request_or_storage_unknown"
        except (
            PermissionError,
            ApplicationError,
            ResourceBudgetError,
            SourceAccessUnavailableError,
            RetentionPolicyUnavailableError,
        ):
            status, reason = (
                "unknown" if meter.admitted else "blocked",
                "source_icon_admission_changed",
            )
        except (ValueError, UnicodeError):
            status, reason = (
                "unknown" if objects_staged else "missing",
                "source_icon_storage_unknown"
                if objects_staged
                else "source_icon_invalid_or_unavailable",
            )
        finally:
            for value in clients:
                value.close()
            meter.close()
            if owned_storage is not None:
                owned_storage.close()
        try:
            with self.sessions.begin() as session:
                execution(session).require_current_lease_allowing_cancel_in_transaction(meter.lease)
                SourceIconService(session, clock=self.clock).finish_in_transaction(
                    seed=seed, job_id=message.job_id, status=status, reason=reason
                )
        except (
            ApplicationError,
            JobExecutionError,
            SourceAccessUnavailableError,
            RetentionPolicyUnavailableError,
        ):
            try:
                with self.sessions.begin() as session:
                    execution(session).require_current_lease_allowing_cancel_in_transaction(
                        meter.lease
                    )
                    SourceIconService(session, clock=self.clock).finish_in_transaction(
                        seed=seed,
                        job_id=message.job_id,
                        status="unknown",
                        reason="source_icon_admission_changed",
                    )
            except (ApplicationError, JobExecutionError):
                pass
            return JobCompletion(
                status=JobStatus.PARTIALLY_SUCCEEDED,
                failure=self._failure("source_icon_admission_changed"),
            )
        return (
            JobCompletion(status=JobStatus.SUCCEEDED)
            if status in {"ready", "missing"}
            else JobCompletion(
                status=JobStatus.PARTIALLY_SUCCEEDED,
                failure=self._failure(reason or "source_icon_result_unknown"),
            )
        )
