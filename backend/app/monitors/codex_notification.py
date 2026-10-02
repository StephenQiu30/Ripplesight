"""Live permission and fixed event/post projection for the original notification ledger."""

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from connections.editorial_services import require_official_x_connection_in_transaction
from core.errors import ApplicationError
from evidence.schemas import DataClass
from evidence.services import (
    RetentionPolicyUnavailableError,
    SourceAccessPolicyService,
    SourceAccessUnavailableError,
)
from monitors.codex_models import CodexResetEvent, CodexResetPost, CodexResetRecognition
from monitors.codex_schemas import (
    CodexContract,
    NotificationIntent,
    ResetEventView,
    ResetPostView,
)
from monitors.codex_services import CodexResetService
from sources.contracts import SourceCapability


class CodexNotificationMaterial(CodexContract):
    monitor_id: UUID
    monitor_revision: int
    configuration_version: int
    source_policy_version: int
    intent: NotificationIntent
    event: ResetEventView
    post: ResetPostView
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


def _canonical_value(value: object) -> object:
    """Hash timestamps by instant, independent of the database session time zone."""
    if isinstance(value, datetime):
        if value.utcoffset() is None:
            raise ValueError("Codex notification timestamps must be timezone-aware")
        return value.astimezone(UTC).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, CodexContract):
        return _canonical_value(value.model_dump(mode="python"))
    if isinstance(value, Mapping):
        return {key: _canonical_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_canonical_value(item) for item in value]
    return value


def read_codex_notification_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    monitor_id: UUID,
    intent: NotificationIntent,
    now: datetime,
) -> CodexNotificationMaterial | None:
    if not session.in_transaction():
        raise RuntimeError("Codex notification reads require the caller transaction")
    service = CodexResetService(session, clock=lambda: now)
    try:
        monitor = service._monitor(owner_id, monitor_id, lock=True)
        configuration = service._configuration(monitor)
        if (
            not monitor.enabled
            or configuration.connection_id is None
            or configuration.connection_version is None
        ):
            return None
        require_official_x_connection_in_transaction(
            session,
            owner_id=owner_id,
            connection_id=configuration.connection_id,
            connection_version=configuration.connection_version,
            now=now,
        )
    except (ApplicationError, SourceAccessUnavailableError, RetentionPolicyUnavailableError):
        return None
    post = session.scalar(
        select(CodexResetPost).where(
            CodexResetPost.owner_id == owner_id,
            CodexResetPost.monitor_id == monitor_id,
            CodexResetPost.id == intent.post_id,
        )
    )
    event = session.scalar(
        select(CodexResetEvent).where(
            CodexResetEvent.owner_id == owner_id,
            CodexResetEvent.monitor_id == monitor_id,
            CodexResetEvent.id == intent.event_id,
        )
    )
    if (
        post is None
        or event is None
        or post.needs_review
        or post.processed_at is None
        or intent.content_at != post.published_at
        or post.published_at <= now - timedelta(hours=36)
        or (intent.action == "withdraw" and not event.withdrawn)
        or (intent.action != "withdraw" and event.withdrawn)
        or (intent.action == "confirm" and event.status != "confirmed")
        or (intent.action in ("announce", "amend") and event.status != "announced")
    ):
        return None
    rows = session.scalars(
        select(CodexResetRecognition).where(
            CodexResetRecognition.owner_id == owner_id,
            CodexResetRecognition.monitor_id == monitor_id,
            CodexResetRecognition.post_id == post.id,
            CodexResetRecognition.status.in_(("applied", "held")),
        )
    )
    if not any(
        intent == NotificationIntent.model_validate(candidate)
        for row in rows
        for candidate in row.notifications
    ):
        return None
    try:
        permission = SourceAccessPolicyService(
            session, clock=lambda: now
        ).admit_payload_in_transaction(
            owner_id=owner_id,
            source_key="x",
            capability=SourceCapability.SEARCH,
            data_class=DataClass.STRUCTURED,
            collected_at=post.published_at,
            payload={"body": str(post.source_input["text"])},
        )
    except (SourceAccessUnavailableError, RetentionPolicyUnavailableError):
        return None
    if "body" not in permission.fields:
        return None
    event_view = service._event_view(event, now=now)
    value = dict(
        monitor_id=monitor.id,
        monitor_revision=monitor.revision,
        configuration_version=monitor.configuration_version,
        source_policy_version=permission.policy_version,
        intent=intent,
        event=event_view,
        post=service._post_view(post),
    )
    canonical = {key: _canonical_value(item) for key, item in value.items()}
    canonical["event"] = _canonical_value(
        event_view.model_dump(mode="python", exclude={"title", "presentation_status"})
    )
    digest = hashlib.sha256(
        json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return CodexNotificationMaterial(**value, sha256=digest)
