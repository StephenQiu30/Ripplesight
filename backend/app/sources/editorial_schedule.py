"""Existing Jobs/Outbox admission; persistent profile due points are the only cursor."""

from datetime import datetime
from uuid import UUID, uuid5

from sqlalchemy.orm import Session

from connections.editorial_group import freeze_due_editorial_groups_in_transaction
from connections.editorial_schemas import EditorialPollInput
from connections.editorial_services import (
    EditorialSourceService,
    list_due_editorial_sources_in_transaction,
)
from core.errors import ApplicationError
from jobs.editorial_member import load_active_editorial_profile_ids_in_transaction
from jobs.schemas import JobAcceptanceInput, JobObservationContext
from jobs.services import JobService
from sources.contracts import SourceCapability

_NAMESPACE = UUID("a1b9c548-1790-45ad-bfe7-e7149b30a0ed")


def enqueue_due_editorial_sources_in_transaction(
    session: Session,
    now: datetime,
    *,
    enabled: bool,
    limit: int = 200,
) -> int:
    if not session.in_transaction() or now.utcoffset() is None:
        raise RuntimeError("source scheduler admission requires aware caller transaction")
    if not enabled:
        return 0
    count = 0
    service = EditorialSourceService(session, clock=lambda: now)
    for manifest in freeze_due_editorial_groups_in_transaction(session, now=now, limit=limit):
        with session.begin_nested():
            JobService(session, clock=lambda: now).accept_in_transaction(
                owner_id=manifest.owner_id,
                command=JobAcceptanceInput(
                    operation_id=uuid5(_NAMESPACE, f"group:{manifest.sha256}"),
                    kind="source.editorial.x_group",
                    observation=JobObservationContext(
                        configuration_ref=f"editorial-group:{manifest.sha256}",
                        configuration_version=1,
                        source_key="x",
                        source_capability=SourceCapability.SEARCH,
                    ),
                    scheduled_for_at=manifest.scheduled_for_at or now,
                    scope={
                        "editorial_group": manifest.model_dump_json(),
                        "group_hash": manifest.sha256,
                    },
                ),
            )
        count += 1
    for due in list_due_editorial_sources_in_transaction(session, now=now, limit=limit):
        if due.profile_id in load_active_editorial_profile_ids_in_transaction(
            session, owner_id=due.owner_id
        ):
            continue
        operation = uuid5(
            _NAMESPACE,
            f"{due.owner_id}:{due.profile_id}:{due.configuration_version}:{due.revision}:"
            f"{due.due_at.isoformat()}",
        )
        try:
            with session.begin_nested():
                service.enqueue_poll_in_transaction(
                    owner_id=due.owner_id,
                    profile_id=due.profile_id,
                    command=EditorialPollInput(
                        operation_id=operation,
                        expected_revision=due.revision,
                        reason="Scheduled editable source poll",
                    ),
                    scheduled_for_at=due.due_at,
                )
            count += 1
        except ApplicationError:
            # A revoked policy or obsolete configuration cannot enqueue a paid request.
            continue
    return count
