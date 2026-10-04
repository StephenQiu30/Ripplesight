"""Freeze the exact post/comment observations used by one analysis prompt batch."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from content.analysis_schemas import AnalysisObservationManifest
from content.models import ContentObservation, ContentRecord
from content.observation_inputs import freeze_observation_inputs_in_transaction
from core.errors import ApplicationError


def _require_exact_roots(
    session: Session, *, owner_id: UUID, manifest: AnalysisObservationManifest
) -> None:
    expected = {
        observation_id: (version_id, "post")
        for version_id, observation_id in manifest.post_observations.items()
    }
    expected.update(
        {
            observation_id: (version_id, "comment")
            for version_id, observation_id in manifest.comment_observations.items()
        }
    )
    rows = session.execute(
        select(
            ContentObservation.id, ContentObservation.content_version_id, ContentRecord.object_type
        )
        .join(
            ContentRecord,
            (ContentRecord.owner_id == ContentObservation.owner_id)
            & (ContentRecord.id == ContentObservation.content_id),
        )
        .where(ContentObservation.owner_id == owner_id, ContentObservation.id.in_(expected))
    ).all()
    if {identifier: (version, kind) for identifier, version, kind in rows} != expected:
        raise ApplicationError("editorial_material_unavailable")


def freeze_analysis_observation_inputs_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    post_observations: dict[UUID, UUID],
    comment_observations: dict[UUID, UUID],
    now: datetime,
) -> AnalysisObservationManifest:
    if not session.in_transaction() or now.utcoffset() is None:
        raise RuntimeError("analysis inputs require caller transaction and aware time")
    roots = tuple(sorted({*post_observations.values(), *comment_observations.values()}, key=str))
    closure = freeze_observation_inputs_in_transaction(
        session, owner_id=owner_id, observation_ids=roots, now=now
    )
    manifest = AnalysisObservationManifest(
        post_observations=dict(sorted(post_observations.items(), key=lambda pair: str(pair[0]))),
        comment_observations=dict(
            sorted(comment_observations.items(), key=lambda pair: str(pair[0]))
        ),
        input_observation_ids=closure,
    )
    _require_exact_roots(session, owner_id=owner_id, manifest=manifest)
    return manifest


def require_analysis_observation_inputs_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    manifest: AnalysisObservationManifest,
    now: datetime,
) -> None:
    if not session.in_transaction() or now.utcoffset() is None:
        raise RuntimeError("analysis inputs require caller transaction and aware time")
    manifest = AnalysisObservationManifest.model_validate(manifest.model_dump(mode="json"))
    _require_exact_roots(session, owner_id=owner_id, manifest=manifest)
    closure = freeze_observation_inputs_in_transaction(
        session,
        owner_id=owner_id,
        observation_ids=tuple(
            sorted(
                {*manifest.post_observations.values(), *manifest.comment_observations.values()},
                key=str,
            )
        ),
        now=now,
    )
    if closure != manifest.input_observation_ids:
        raise ApplicationError("editorial_material_unavailable")


def analysis_observation_manifests_readable_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    manifests: tuple[AnalysisObservationManifest, ...],
    now: datetime,
) -> dict[str, bool]:
    """Read shared facts once; retain each exact batch's separate ALL decision."""
    from content.observation_reading import readable_observation_groups_in_transaction

    if not session.in_transaction() or now.utcoffset() is None or len(manifests) > 2000:
        raise ValueError("bounded analysis manifests require aware caller transaction")
    distinct = {manifest.signature: manifest for manifest in manifests}
    result = {}
    items = tuple(distinct.items())
    for start in range(0, len(items), 100):
        batch = dict(items[start : start + 100])
        roots = {
            key: tuple(
                sorted({*m.post_observations.values(), *m.comment_observations.values()}, key=str)
            )
            for key, m in batch.items()
        }
        closures = readable_observation_groups_in_transaction(
            session, owner_id=owner_id, observation_groups=roots, now=now
        )
        identifiers = tuple({i for values in roots.values() for i in values})
        found: dict[UUID, tuple[UUID | None, str]] = {}
        for offset in range(0, len(identifiers), 1000):
            found.update(
                (identifier, (version, kind))
                for identifier, version, kind in session.execute(
                    select(
                        ContentObservation.id,
                        ContentObservation.content_version_id,
                        ContentRecord.object_type,
                    )
                    .join(
                        ContentRecord,
                        (ContentRecord.owner_id == ContentObservation.owner_id)
                        & (ContentRecord.id == ContentObservation.content_id),
                    )
                    .where(
                        ContentObservation.owner_id == owner_id,
                        ContentObservation.id.in_(identifiers[offset : offset + 1000]),
                    )
                )
            )
        for key, manifest in batch.items():
            expected = {
                obs: (version, "post") for version, obs in manifest.post_observations.items()
            }
            expected.update(
                (obs, (version, "comment"))
                for version, obs in manifest.comment_observations.items()
            )
            result[key] = closures.get(key) == manifest.input_observation_ids and all(
                found.get(obs) == pair for obs, pair in expected.items()
            )
    return result
