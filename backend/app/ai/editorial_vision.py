"""One actual first-image input for an admitted editorial understand stage."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import httpx
from sqlalchemy.orm import Session, sessionmaker

from ai.capability_services import load_frozen_ai_routing_in_transaction
from ai.schemas import AiCallError, AiFailureCode, AiImageInput
from content.editorial_rendered import read_editorial_rendered_in_transaction
from content.editorial_vision import read_editorial_vision_grant_in_transaction
from content.schemas import EventContentReadReference
from core.config import Settings
from evidence.services import LifecycleService, load_readable_resources_in_transaction
from jobs.execution import ExecutionLease
from jobs.schemas import JobMessage
from jobs.services import ResourceBudgetError
from publication.media_mirror_fetch import MediaMirrorClient, Resolver, resolve_public_addresses
from publication.media_mirror_meter import MediaRequestMeter


@dataclass(frozen=True)
class EditorialVisionInput:
    image: AiImageInput | None
    mode: str
    evidence_id: UUID | None = None
    resource_id: UUID | None = None
    rendered_sha256: str | None = None


def prepare_editorial_vision_input(
    sessions: sessionmaker[Session],
    *,
    settings: Settings,
    message: JobMessage,
    lease: ExecutionLease,
    reference: EventContentReadReference,
    stage_id: UUID,
    guard: Callable[[Session], object],
    clock: Callable[[], datetime],
    transport: httpx.BaseTransport | None = None,
    resolver: Resolver = resolve_public_addresses,
) -> EditorialVisionInput:
    if not settings.ai_enabled or not getattr(settings, "ai_vision_requests_enabled", False):
        return EditorialVisionInput(None, "text_disabled")
    with sessions.begin() as session:
        guard(session)
        routing = load_frozen_ai_routing_in_transaction(
            session, owner_id=message.owner_id, job_id=message.job_id
        )
        if routing is None or not routing.for_purpose("editorial.understand").vision:
            return EditorialVisionInput(None, "text_model")
        grant = read_editorial_vision_grant_in_transaction(
            session, owner_id=message.owner_id, reference=reference, now=clock()
        )
        if grant is None:
            rendered = read_editorial_rendered_in_transaction(
                session,
                owner_id=message.owner_id,
                content_id=reference.content_id,
                content_version_id=reference.content_version_id,
                now=clock(),
            )
            if rendered is not None and any(m.kind == "image" for m in rendered.media):
                raise AiCallError(
                    AiFailureCode.UNAVAILABLE, "first-image permission has not been approved"
                )
            return EditorialVisionInput(None, "text_no_image")
        evidence = LifecycleService(session, clock=clock).track_resource_in_transaction(
            owner_id=message.owner_id,
            resource_type="ai_vision_input",
            resource_id=stage_id,
            admission=grant.admission,
            cleanup_targets=[],
        )

    def live(session: Session) -> None:
        guard(session)
        current = read_editorial_vision_grant_in_transaction(
            session, owner_id=message.owner_id, reference=reference, now=clock()
        )
        readable = load_readable_resources_in_transaction(
            session,
            owner_id=message.owner_id,
            resource_type="ai_vision_input",
            resource_ids={evidence.resource_id},
            now=clock(),
        )
        if current != grant or evidence.resource_id not in readable:
            raise PermissionError("current first-image permission changed")

    meter = MediaRequestMeter(
        sessions,
        message,
        lease,
        clock=clock,
        source_key=grant.admission.source_key,
        lease_seconds=settings.job_lease_seconds,
        guard=live,
        component_key="ai.vision.fetch",
        budget_job_ref=f"job:{message.job_id.hex}",
        stage_prefix="ai.vision",
    )
    client = MediaMirrorClient(
        enabled=True,
        before_request=lambda index: meter.before(stage_id, "http", index),
        after_request=lambda index, outcome: meter.after(stage_id, "http", index, outcome),
        resolver=resolver,
        transport=transport,
        image_max_bytes=4_000_000,
    )
    try:
        fetched = client.fetch(grant.url, kind="image")
        image = AiImageInput(body=fetched.body, content_type=fetched.mime_type)
        with sessions.begin() as session:
            live(session)
        return EditorialVisionInput(
            image, "image", evidence.id, evidence.resource_id, grant.rendered_sha256
        )
    except (httpx.TransportError, TimeoutError, OSError):
        raise AiCallError(
            AiFailureCode.TIMEOUT, "first-image request outcome is unknown", outcome_unknown=True
        ) from None
    except ValueError:
        return EditorialVisionInput(None, "text_unsupported_image")
    except ResourceBudgetError:
        raise AiCallError(
            AiFailureCode.UNAVAILABLE, "first-image request admission was denied before sending"
        ) from None
    except PermissionError:
        raise AiCallError(
            AiFailureCode.UNAVAILABLE,
            "first-image input requires review",
            outcome_unknown=bool(meter.admitted),
        ) from None
    finally:
        client.close()
        meter.close()
