"""Complete content dependency candidates for lock-free independent authority reads."""

import hashlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from content.models import (
    ContentObservation,
    ContentObservationInput,
    ContentRecord,
    ContentVersion,
)
from content.observation_context import load_observation_contexts_in_transaction
from content.observation_reading import readable_observation_groups_in_transaction
from core.errors import ApplicationError, AuthorityUnavailableError
from evidence.admission_reading import load_current_source_admissions_in_transaction
from evidence.schemas import DataClass
from evidence.services import (
    load_readable_resources_in_transaction,
    load_source_access_policy_in_transaction,
    load_source_access_readiness,
)


@dataclass(frozen=True, slots=True)
class ContentAuthorityProof:
    """A single action's exact candidate, never a reusable allow token."""

    resources: frozenset[tuple[str, UUID]]
    fingerprint: str


def require_unowned_transaction(session: Session) -> Engine:
    """Refuse caller transactions without rolling them back or issuing journal I/O."""
    bind = session.get_bind()
    if session.in_transaction() or not isinstance(bind, Engine):
        raise AuthorityUnavailableError()
    return bind


@contextmanager
def content_read_snapshot(session: Session) -> Iterator[None]:
    """Own one new read-only snapshot and reject residual backend advisory locks."""
    require_unowned_transaction(session)
    session.expire_all()
    with session.begin():
        connection = session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        connection.exec_driver_sql("SET TRANSACTION READ ONLY")
        if connection.execute(
            text("""
            SELECT EXISTS(SELECT 1 FROM pg_locks
            WHERE pid=pg_backend_pid() AND locktype='advisory' AND granted)
        """)
        ).scalar_one():
            raise AuthorityUnavailableError()
        yield


def freeze_content_authority_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    roots: set[UUID],
    additional_resources: set[tuple[str, UUID]],
    output: object,
    now: datetime,
) -> ContentAuthorityProof:
    """Freeze complete original edges, source policy versions and output semantics.

    The caller supplies every actual output dependency. This function performs
    no journal I/O and cannot own or end a caller's write transaction.
    """
    if not roots or len(roots) > 2000:
        raise ApplicationError("resource_not_found")
    closure = readable_observation_groups_in_transaction(
        session,
        owner_id=owner_id,
        observation_groups={"detail": tuple(sorted(roots, key=str))},
        now=now,
        include_metadata=True,
    )["detail"]
    if closure is None:
        raise ApplicationError("resource_not_found")
    identifiers = set(closure)
    contexts = load_observation_contexts_in_transaction(
        session, owner_id=owner_id, observation_ids=identifiers
    )
    if set(contexts) != identifiers:
        raise ApplicationError("resource_not_found")
    source_contexts = {(c.source_key, c.job.source_capability) for c in contexts.values()}
    readiness = load_source_access_readiness(session, owner_id=owner_id, now=now)
    admissions = {}
    ordered_contexts = sorted(source_contexts, key=lambda item: (item[0], item[1]))
    for start in range(0, len(ordered_contexts), 1000):
        admissions.update(
            load_current_source_admissions_in_transaction(
                session,
                owner_id=owner_id,
                source_contexts=set(ordered_contexts[start : start + 1000]),
                data_class=DataClass.STRUCTURED,
                now=now,
            )
        )
    if set(admissions) != source_contexts or not all(
        readiness.get(key, False) for key in source_contexts
    ):
        raise ApplicationError("resource_not_found")
    evidence = {}
    ordered = tuple(sorted(identifiers, key=str))
    for start in range(0, len(ordered), 1000):
        evidence.update(
            load_readable_resources_in_transaction(
                session,
                owner_id=owner_id,
                resource_type="content_observation",
                resource_ids=set(ordered[start : start + 1000]),
                now=now,
            )
        )
    if set(evidence) != identifiers:
        raise ApplicationError("resource_not_found")
    observations = list(
        session.execute(
            select(ContentObservation.__table__)
            .where(ContentObservation.owner_id == owner_id, ContentObservation.id.in_(identifiers))
            .order_by(ContentObservation.id)
        ).mappings()
    )
    versions = {
        row["content_version_id"] for row in observations if row["content_version_id"] is not None
    }
    contents = {row["content_id"] for row in observations}
    rows = {
        "observations": [dict(row) for row in observations],
        "versions": [
            dict(row)
            for row in session.execute(
                select(ContentVersion.__table__)
                .where(ContentVersion.owner_id == owner_id, ContentVersion.id.in_(versions))
                .order_by(ContentVersion.id)
            ).mappings()
        ],
        "contents": [
            dict(row)
            for row in session.execute(
                select(ContentRecord.__table__)
                .where(ContentRecord.owner_id == owner_id, ContentRecord.id.in_(contents))
                .order_by(ContentRecord.id)
            ).mappings()
        ],
        "edges": [
            tuple(row)
            for row in session.execute(
                select(
                    ContentObservationInput.output_observation_id,
                    ContentObservationInput.input_observation_id,
                )
                .where(
                    ContentObservationInput.owner_id == owner_id,
                    ContentObservationInput.output_observation_id.in_(identifiers),
                )
                .order_by(
                    ContentObservationInput.output_observation_id,
                    ContentObservationInput.input_observation_id,
                )
            )
        ],
        "contexts": [asdict(contexts[key]) for key in ordered],
        "admissions": [asdict(admissions[key]) for key in ordered_contexts],
        "policies": [
            policy.model_dump(mode="json") if policy is not None else None
            for key, capability in ordered_contexts
            for policy in (
                load_source_access_policy_in_transaction(
                    session, owner_id=owner_id, source_key=key, capability=capability, lock=False
                ),
            )
        ],
        "evidence": [evidence[key].model_dump(mode="json") for key in ordered],
        "output": output,
    }
    return ContentAuthorityProof(
        frozenset({("content_observation", key) for key in identifiers} | additional_resources),
        hashlib.sha256(
            json.dumps(rows, default=str, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    )
