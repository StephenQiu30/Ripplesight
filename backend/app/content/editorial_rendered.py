"""One immutable representation per original version; reads obey original Evidence."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from urllib.parse import urljoin
from uuid import UUID

from bs4 import BeautifulSoup
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from content.editorial_rendered_models import ContentRenderedMaterial
from content.editorial_rendered_schemas import (
    EditorialRenderedMedia,
    EditorialRenderedRepresentation,
    EditorialRenderedView,
)
from content.event_reading import load_event_member_content_in_transaction
from content.models import ContentObservation
from content.schemas import EventContentReadReference
from core.errors import ApplicationError
from evidence.schemas import DataClass
from evidence.services import (
    RetentionPolicyUnavailableError,
    SourceAccessPolicyService,
    SourceAccessUnavailableError,
)
from jobs.services import load_content_job_context
from sources.editorial_html import safe_srcset, sanitize_editorial_html
from sources.editorial_schemas import EditorialMaterial, public_url


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def prepare_editorial_rendered(material: EditorialMaterial) -> EditorialRenderedRepresentation:
    """Freeze collector-declared format and all media, without guessing from text."""
    body_format = material.content_format if material.body_status == "ok" else "text"
    body = (
        material.body_html
        if body_format == "html"
        else material.body_markdown
        if body_format == "markdown"
        else material.body_text
    )
    body = body if material.body_status == "ok" else material.excerpt
    body = body or ""
    representation_hash = _digest(
        {
            "format": body_format,
            "body": body,
            "media": material.media,
            "media_details": [m.model_dump(mode="json") for m in material.media_details],
        }
    )
    media: list[EditorialRenderedMedia] = []
    seen: set[str] = set()

    def add(url: str, kind: str = "unknown", alt: str | None = None, origin: str = "body") -> None:
        try:
            parsed = EditorialRenderedMedia(
                url=public_url(urljoin(material.url, url)),
                kind=kind,
                alt=alt,
                origin=origin,
            )
        except ValueError:
            return
        if parsed.url not in seen and len(media) < 64:
            media.append(parsed)
            seen.add(parsed.url)

    if body_format == "html":
        body = sanitize_editorial_html(body, material.url)
        soup = BeautifulSoup(body, "html.parser")
        for node in soup.find_all(True):
            attrs = node.attrs
            if node.name in ("img", "video", "audio", "source") and "src" in attrs:
                add(
                    str(attrs["src"]),
                    "image"
                    if node.name == "img"
                    else "video"
                    if node.name == "video"
                    else "audio"
                    if node.name == "audio"
                    else "unknown",
                    str(attrs["alt"]) if "alt" in attrs else None,
                )
            if "poster" in attrs:
                add(str(attrs["poster"]), "image")
            if isinstance(attrs.get("srcset"), str):
                for url, _ in safe_srcset(str(attrs["srcset"]), material.url):
                    add(url, "image")
    elif body_format == "markdown":
        for match in re.finditer(r"!\[([^\]\n]{0,512})\]\(([^\s)]+)(?:\s+[^)]*)?\)", body):
            add(match[2], "image", match[1] or None)
    details = {item.url: item for item in material.media_details}
    for url in material.media:
        detail = details.get(url)
        add(url, detail.kind if detail else "unknown", detail.alt if detail else None, "attachment")
    canonical = {
        "body_format": body_format,
        "body": body,
        "media": [item.model_dump(mode="json") for item in media],
        "representation_sha256": representation_hash,
    }
    return EditorialRenderedRepresentation(**canonical, sha256=_digest(canonical))


def save_editorial_rendered_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    content_id: UUID,
    content_version_id: UUID,
    representation: EditorialRenderedRepresentation,
    now: datetime,
) -> EditorialRenderedView:
    if not session.in_transaction():
        raise RuntimeError("rendered writes require the caller's transaction")
    # The observation and its server-approved field/retention policy must already exist.
    reference = EventContentReadReference(
        content_id=content_id, content_version_id=content_version_id
    )
    readable = load_event_member_content_in_transaction(
        session, owner_id=owner_id, references=(reference,), now=now
    ).get(reference)
    if (
        readable is None
        or readable.current_visibility is None
        or readable.current_visibility.status != "visible"
    ):
        raise ApplicationError("editorial_material_unavailable")
    session.execute(
        insert(ContentRenderedMaterial)
        .values(
            owner_id=owner_id,
            content_id=content_id,
            content_version_id=content_version_id,
            body_format=representation.body_format,
            body=representation.body,
            media=[item.model_dump(mode="json") for item in representation.media],
            representation_hash=bytes.fromhex(representation.representation_sha256),
            input_hash=bytes.fromhex(representation.sha256),
            created_at=now,
        )
        .on_conflict_do_nothing(index_elements=["owner_id", "content_version_id"])
    )
    row = session.get(ContentRenderedMaterial, (owner_id, content_version_id))
    if row is None or row.content_id != content_id or row.input_hash.hex() != representation.sha256:
        raise ApplicationError("editorial_version_conflict")
    return EditorialRenderedView(
        content_id=content_id, content_version_id=content_version_id, **representation.model_dump()
    )


def read_editorial_rendered_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    content_id: UUID,
    content_version_id: UUID,
    now: datetime,
    observation_id: UUID | None = None,
) -> EditorialRenderedView | None:
    if not session.in_transaction():
        raise RuntimeError("rendered reads require the caller's transaction")
    reference = EventContentReadReference(
        content_id=content_id, content_version_id=content_version_id, observation_id=observation_id
    )
    readable = load_event_member_content_in_transaction(
        session, owner_id=owner_id, references=(reference,), now=now
    ).get(reference)
    if (
        readable is None
        or readable.current_visibility is None
        or readable.current_visibility.status != "visible"
    ):
        return None
    row = session.get(ContentRenderedMaterial, (owner_id, content_version_id))
    if row is None or row.content_id != content_id:
        return None
    observation = session.get(ContentObservation, readable.observation.id)
    context = (
        load_content_job_context(session, owner_id=owner_id, job_id=observation.job_id)
        if observation is not None
        else None
    )
    if context is None or context.source_capability is None:
        return None
    try:
        admission = SourceAccessPolicyService(
            session, clock=lambda: now
        ).admit_payload_in_transaction(
            owner_id=owner_id,
            source_key=readable.source_key,
            capability=context.source_capability,
            data_class=DataClass.STRUCTURED,
            collected_at=readable.observation.observed_at,
            payload={"body": row.body, "media": [str(item["url"]) for item in row.media]},
        )
    except (SourceAccessUnavailableError, RetentionPolicyUnavailableError):
        return None
    if row.body and "body" not in admission.fields:
        return None
    if (
        any(item.get("origin") == "attachment" for item in row.media)
        and "media" not in admission.fields
    ):
        return None
    return EditorialRenderedView(
        content_id=content_id,
        content_version_id=content_version_id,
        body_format=row.body_format,
        body=row.body,
        media=row.media,
        representation_sha256=row.representation_hash.hex(),
        sha256=row.input_hash.hex(),
    )
