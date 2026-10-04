"""Scrub retained analysis prompt copies without changing original Job audit state."""

from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from analysis.schemas import AnalysisJobScope
from jobs.models import Job


def purge_analysis_job_materials_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    observation_ids: tuple[UUID, ...],
    content_version_ids: tuple[UUID, ...],
    legacy_content_version_ids: tuple[UUID, ...],
) -> None:
    """Remove only prompt_items; immutable references, status and counters stay intact.

    Modern Jobs freeze the exact observation closure, so another lawful alias of
    the same version is independent. Legacy Jobs have only their original post
    and comment versions. An incomplete scope cannot prove its text independent
    and is scrubbed conservatively. Pending Jobs need this cleanup as well as
    successful original Jobs referenced by an AI call.
    """
    if not session.in_transaction():
        raise RuntimeError("Job content cleanup requires the caller transaction")
    if max(len(observation_ids), len(content_version_ids), len(legacy_content_version_ids)) > 10000:
        raise ValueError("Job content cleanup exceeds bounded deletion inputs")
    observations = set(observation_ids)
    versions = set(content_version_ids)
    legacy_versions = set(legacy_content_version_ids)
    if not (observations or versions or legacy_versions):
        return
    candidates = tuple(
        session.scalars(
            select(Job)
            .where(
                Job.owner_id == owner_id,
                Job.kind == "analysis.annotate",
                Job.scope.has_key("prompt_items"),
            )
            .order_by(Job.id)
            .limit(10001)
            .with_for_update()
        )
    )
    if len(candidates) > 10000:
        raise ValueError("Job content cleanup exceeds bounded original Jobs")
    for job in candidates:
        try:
            scope = AnalysisJobScope.from_job_scope(job.scope)
            if (
                scope.prompt_items is None
                or job.configuration_ref != f"topic:{scope.topic_id}"
                or job.configuration_version != scope.topic_rule_version
                or any(
                    item.comments and item.comment_version_ids is None
                    for item in scope.prompt_items
                )
            ):
                affected = True
            elif scope.input_manifest is not None:
                # Full closure includes every item actually used by this prompt.
                affected = bool(
                    observations.intersection(scope.input_manifest.input_observation_ids)
                    or versions.intersection(scope.input_manifest.post_observations)
                    or versions.intersection(scope.input_manifest.comment_observations)
                )
            else:
                originals = set(scope.content_version_ids)
                originals.update(
                    identifier
                    for item in scope.prompt_items
                    for identifier in item.comment_version_ids or ()
                )
                affected = bool(originals.intersection(versions | legacy_versions))
        except (ValueError, ValidationError):
            affected = True
        if affected:
            cleaned_scope = dict(job.scope)
            cleaned_scope.pop("prompt_items", None)
            job.scope = cleaned_scope
    session.flush()
