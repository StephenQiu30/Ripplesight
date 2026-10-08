"""Bounded call-local graph and ALL permission reads for independent outputs."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from content.models import ContentObservation, ContentVersion
from content.observation_context import (
    load_observation_contexts_in_transaction,
    load_observation_visibilities_in_transaction,
)
from content.observation_inputs import observation_input_closures_in_transaction
from evidence.admission_reading import load_current_source_admissions_in_transaction
from evidence.schemas import DataClass
from evidence.services import load_readable_resources_in_transaction
from sources.editorial_identity import NATIVE_IDENTITY_PURPOSE, EditorialNativeIdentityProof


def readable_observation_groups_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    observation_groups: dict[str, tuple[UUID, ...]],
    now: datetime,
) -> dict[str, tuple[UUID, ...] | None]:
    if not session.in_transaction() or now.utcoffset() is None or len(observation_groups) > 2000:
        raise ValueError("bounded ALL reads require aware caller transaction")
    result: dict[str, tuple[UUID, ...] | None] = {}
    entries = tuple(observation_groups.items())
    for start in range(0, len(entries), 100):
        groups = dict(entries[start : start + 100])
        closures = observation_input_closures_in_transaction(
            session, owner_id=owner_id, observation_groups=groups
        )
        identifiers = {i for closure in closures.values() if closure for i in closure}
        if len(identifiers) > 20000:
            # Aggregate work limits must never turn unrelated inputs into one ALL group.
            for key, roots in groups.items():
                result.update(
                    readable_observation_groups_in_transaction(
                        session, owner_id=owner_id, observation_groups={key: roots}, now=now
                    )
                )
            continue
        leaf_flags = _readable_leaves(session, owner_id=owner_id, identifiers=identifiers, now=now)
        for key, closure in closures.items():
            result[key] = (
                closure if closure and all(leaf_flags.get(i, False) for i in closure) else None
            )
    return result


def _readable_leaves(
    session: Session, *, owner_id: UUID, identifiers: set[UUID], now: datetime
) -> dict[UUID, bool]:
    rows: list[tuple[ContentObservation, ContentVersion]] = []
    original_permissions = {}
    ordered = tuple(identifiers)
    for start in range(0, len(ordered), 1000):
        batch = set(ordered[start : start + 1000])
        rows.extend(
            (observation, version)
            for observation, version in session.execute(
                select(ContentObservation, ContentVersion)
                .join(
                    ContentVersion,
                    (ContentVersion.owner_id == ContentObservation.owner_id)
                    & (ContentVersion.id == ContentObservation.content_version_id)
                    & (ContentVersion.content_id == ContentObservation.content_id),
                )
                .where(ContentObservation.owner_id == owner_id, ContentObservation.id.in_(batch))
                .execution_options(populate_existing=True)
            ).all()
        )
        original_permissions.update(
            load_readable_resources_in_transaction(
                session,
                owner_id=owner_id,
                resource_type="content_observation",
                resource_ids=batch,
                now=now,
            )
        )
    contexts = load_observation_contexts_in_transaction(
        session, owner_id=owner_id, observation_ids=identifiers
    )
    visibility = load_observation_visibilities_in_transaction(
        session, owner_id=owner_id, contexts=contexts, decisive_only=True
    )
    admissions = {}
    source_contexts = tuple({(c.source_key, c.job.source_capability) for c in contexts.values()})
    for start in range(0, len(source_contexts), 1000):
        admissions.update(
            load_current_source_admissions_in_transaction(
                session,
                owner_id=owner_id,
                source_contexts=set(source_contexts[start : start + 1000]),
                data_class=DataClass.STRUCTURED,
                now=now,
            )
        )
    result = dict.fromkeys(identifiers, False)
    for observation, version in rows:
        actual = contexts.get(observation.id)
        original = original_permissions.get(observation.id)
        visible = visibility.get(observation.id)
        if (
            actual is None
            or original is None
            or (visible is not None and visible.status in {"deleted", "restricted"})
        ):
            continue
        admission = admissions.get((actual.source_key, actual.job.source_capability))
        if admission is None:
            continue
        payload: dict[str, object] = {
            field: getattr(version, field) for field in ("title", "body") if getattr(version, field)
        }
        if not payload and version.text_scope == "media_only":
            # A media-only record still needs current permission for its stored semantics.
            payload = {"text_scope": version.text_scope, "text_origin": version.text_origin}
        try:
            if observation.native_identity_proof is not None:
                if admission.field_purposes.get("native_identity") != NATIVE_IDENTITY_PURPOSE:
                    continue
                payload["native_identity"] = EditorialNativeIdentityProof.model_validate(
                    observation.native_identity_proof
                ).model_dump_json()
            admitted = admission.admit(
                collected_at=observation.observed_at, payload=payload, now=now
            )
        except ValueError:
            continue
        result[observation.id] = (
            admitted.policy_id == original.source_policy_id
            and admitted.policy_version == original.source_policy_version
            and admitted.retention_policy_id == original.retention_policy_id
            and admitted.retention_policy_version == original.retention_policy_version
            and admitted.expires_at > now
            and all(admitted.fields.get(key) == value for key, value in payload.items())
        )
    return result
