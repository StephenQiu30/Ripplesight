"""Connection-domain CAS and current grants for read-only source previews."""

from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from connections.editorial_services import EditorialSourceService
from core.errors import ApplicationError
from evidence.services import RetentionPolicyUnavailableError, SourceAccessUnavailableError
from sources.editorial_schemas import EditorialProfileView, fingerprint


def preview_profile_hash(profile: EditorialProfileView) -> str:
    data = profile.model_dump(mode="json")
    return fingerprint(
        {
            name: data[name]
            for name in (
                "id",
                "source_key",
                "enabled",
                "revision",
                "configuration_version",
                "configuration",
                "participation_mode",
                "connection_id",
                "connection_version",
                "policy_version",
            )
        }
    ).hex()


def load_editorial_preview_profile_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    profile_id: UUID,
    expected_revision: int,
    now: datetime,
    require_remote: bool = False,
) -> EditorialProfileView:
    if not session.in_transaction():
        raise RuntimeError("source preview reads require caller transaction")
    service = EditorialSourceService(session, clock=lambda: now)
    profile = service._profile(owner_id, profile_id, lock=True)
    if profile.revision != expected_revision:
        raise ApplicationError("editorial_version_conflict")
    version = service._version(profile)
    if require_remote:
        if not profile.enabled:
            raise ApplicationError("editorial_source_unavailable")
        try:
            service._require_ready(profile, version, now)
        except (SourceAccessUnavailableError, RetentionPolicyUnavailableError):
            raise ApplicationError("editorial_source_unavailable") from None
    return service._view(profile)
