"""One content transaction: approved policy -> admitted payload -> existing facts/evidence."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid5

from sqlalchemy.orm import Session

from connections.schemas import SourceEntryPoint
from content.editorial_rendered import (
    prepare_editorial_rendered,
    save_editorial_rendered_in_transaction,
)
from content.editorial_schemas import EditorialContentInput, EditorialContentResult
from content.schemas import PersistContentPostInput
from content.services import ContentService
from content.topic_matches import match_editorial_content_in_transaction
from core.errors import ApplicationError
from evidence.schemas import DataClass
from evidence.services import SourceAccessPolicyService


class EditorialContentIngestService:
    def __init__(
        self, session: Session, *, clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    ) -> None:
        self._session, self._clock = session, clock

    def ingest_in_transaction(
        self, *, owner_id: UUID, command: EditorialContentInput
    ) -> EditorialContentResult:
        if not self._session.in_transaction():
            raise RuntimeError("editorial content ingestion requires the caller's transaction")
        m = command.material
        original_body = m.body_text if m.body_status == "ok" else m.excerpt
        original_body = original_body if original_body and original_body.strip() else None
        payload: dict[str, object] = {
            "object_type": "post",
            "external_id": m.external_id or m.identity_key,
            "identity_basis": "guid" if m.external_id else "url_fallback",
            "canonical_url": m.url,
            "author_name": m.author,
            "published_at": m.published_at.isoformat() if m.published_at else None,
            "text_scope": "full" if m.body_status == "ok" else "summary",
            "text_origin": "source",
            "title": m.title,
            "body": original_body,
        }
        admission = SourceAccessPolicyService(
            self._session, clock=self._clock
        ).admit_payload_in_transaction(
            owner_id=owner_id,
            source_key=command.source_key,
            capability=command.capability,
            data_class=DataClass.STRUCTURED,
            collected_at=command.observed_at,
            payload=payload,
        )
        if admission.policy_version != command.policy_version:
            raise ApplicationError("editorial_version_conflict")
        # A minimized permission cannot silently promote a teaser to a complete body.
        required = {"external_id", "canonical_url", "title", "text_scope", "text_origin"}
        if not required.issubset(admission.fields) or (
            m.body_status == "ok" and "body" not in admission.fields
        ):
            raise ApplicationError("editorial_material_unavailable")
        rendered_admission = SourceAccessPolicyService(
            self._session, clock=self._clock
        ).admit_payload_in_transaction(
            owner_id=owner_id,
            source_key=command.source_key,
            capability=command.capability,
            data_class=DataClass.STRUCTURED,
            collected_at=command.observed_at,
            payload={
                "canonical_url": m.url,
                "body": m.body_html
                if m.content_format == "html"
                else m.body_markdown
                if m.content_format == "markdown"
                else m.body_text
                if m.body_status == "ok"
                else m.excerpt,
                "media": list(m.media),
            },
        )
        if rendered_admission.policy_version != command.policy_version:
            raise ApplicationError("editorial_version_conflict")
        if m.body_status == "ok" and "body" not in rendered_admission.fields:
            raise ApplicationError("editorial_material_unavailable")
        representation = prepare_editorial_rendered(
            m.model_copy(
                update={
                    "media": m.media if "media" in rendered_admission.fields else (),
                    "media_details": m.media_details
                    if "media" in rendered_admission.fields
                    else (),
                    "body_text": m.body_text if "body" in admission.fields else None,
                    "excerpt": m.excerpt if "body" in admission.fields else None,
                }
            )
        )
        result = ContentService(self._session, clock=self._clock).persist_post_in_transaction(
            owner_id=owner_id,
            command=PersistContentPostInput(
                job_id=command.job_id,
                source_operation_id=uuid5(command.operation_id, m.identity_key),
                connection_id=command.connection_id,
                connection_version=command.connection_version,
                entry_point=SourceEntryPoint.MANUAL
                if command.first_import
                else SourceEntryPoint.SCHEDULED,
                component_name="editorial-source",
                component_version="aihot-035f7b7f-v1",
                native_scope=f"editorial-profile:{command.profile_id}",
                admission=admission,
            ),
            representation_fingerprint=bytes.fromhex(representation.sha256),
            member_profile_id=command.profile_id if command.grouped_job else None,
        )
        version = result.latest_observation.content_version
        if version is None:
            raise ApplicationError("editorial_material_unavailable")
        save_editorial_rendered_in_transaction(
            self._session,
            owner_id=owner_id,
            content_id=result.id,
            content_version_id=version.id,
            representation=representation,
            now=self._clock(),
        )
        match_editorial_content_in_transaction(
            self._session,
            owner_id=owner_id,
            profile_id=command.profile_id,
            profile_configuration_version=command.configuration_version,
            content_id=result.id,
            content_version_id=version.id,
            observation_id=result.latest_observation.id,
            job_id=command.job_id,
            connection_id=command.connection_id,
            connection_version=command.connection_version,
            policy_version=command.policy_version,
            now=self._clock(),
            grouped_job=command.grouped_job,
        )
        return EditorialContentResult(
            content_id=result.id,
            content_version_id=version.id,
            observation_id=result.latest_observation.id,
        )
