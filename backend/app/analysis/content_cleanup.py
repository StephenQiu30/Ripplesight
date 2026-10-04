"""Analysis-owned physical cleanup for content lifecycle, inside its original transaction."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from analysis.editorial_models import EditorialContentState, EditorialOverride, EditorialRun
from analysis.models import ContentAnnotation
from analysis.translation_models import ContentTranslationBatch, ContentTranslationRun


def purge_analysis_content_inputs_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    content_version_ids: tuple[UUID, ...],
    now: datetime,
    observation_ids: tuple[UUID, ...] = (),
    legacy_content_version_ids: tuple[UUID, ...] = (),
) -> None:
    if not session.in_transaction():
        raise RuntimeError("analysis cleanup requires caller transaction")

    def uses(value: object) -> bool:
        if isinstance(value, str):
            return value in {str(i) for i in observation_ids}
        if isinstance(value, dict):
            return any(uses(item) for item in value.values())
        if isinstance(value, list):
            return any(uses(item) for item in value)
        return False

    def legacy_annotation_uses(item: ContentAnnotation) -> bool:
        if item.input_manifest is not None:
            return False
        if item.content_version_id in legacy_content_version_ids:
            return True
        if not (item.summary or item.relevance_reason or item.viewpoints):
            return False
        from pydantic import ValidationError

        from ai.analysis_reading import load_legacy_analysis_call_job_in_transaction
        from analysis.schemas import AnalysisJobScope
        from jobs.services import load_job_execution_configuration

        if item.ai_call_id is None:
            return True  # Unproven derived text cannot survive an original-input deletion.
        job_id = load_legacy_analysis_call_job_in_transaction(
            session,
            owner_id=owner_id,
            ai_call_id=item.ai_call_id,
            prompt_version=item.prompt_version,
        )
        configuration = load_job_execution_configuration(session, job_id=job_id) if job_id else None
        if (
            configuration is None
            or configuration.owner_id != owner_id
            or configuration.kind != "analysis.annotate"
        ):
            return True
        try:
            scope = AnalysisJobScope.from_job_scope(configuration.scope)
        except (ValidationError, ValueError):
            return True
        if (
            scope.input_manifest is not None
            or scope.topic_id != item.topic_id
            or scope.topic_rule_version != item.topic_rule_version
            or scope.prompt_version != item.prompt_version
            or item.content_version_id not in scope.content_version_ids
            or configuration.observation.configuration_ref != f"topic:{scope.topic_id}"
            or configuration.observation.configuration_version != scope.topic_rule_version
            or scope.prompt_items is None
            or any(
                prompt.comments and prompt.comment_version_ids is None
                for prompt in scope.prompt_items
            )
        ):
            return True
        originals = set(scope.content_version_ids)
        originals.update(
            version for prompt in scope.prompt_items for version in prompt.comment_version_ids or ()
        )
        return bool(originals.intersection(legacy_content_version_ids))

    annotation_ids = tuple(
        item.id
        for item in session.scalars(
            select(ContentAnnotation)
            .where(ContentAnnotation.owner_id == owner_id)
            .with_for_update()
        )
        if item.content_version_id in content_version_ids
        or uses(item.input_manifest)
        or legacy_annotation_uses(item)
    )
    session.execute(
        delete(ContentAnnotation).where(
            ContentAnnotation.owner_id == owner_id, ContentAnnotation.id.in_(annotation_ids)
        )
    )
    affected_editorial = tuple(
        run
        for run in session.scalars(
            select(EditorialRun).where(EditorialRun.owner_id == owner_id).with_for_update()
        )
        if run.content_version_id in content_version_ids
        or (
            run.content_version_id in legacy_content_version_ids
            and not run.input_manifest.get("main", {}).get("observation_id")
        )
        or uses(run.input_manifest)
        or (
            run.input_manifest.get("quote", {}).get("content_version_id")
            in {str(i) for i in content_version_ids}
        )
        or (
            run.input_manifest.get("quote", {}).get("content_version_id")
            in {str(i) for i in legacy_content_version_ids}
            and not run.input_manifest.get("quote", {}).get("observation_id")
        )
    )
    affected_run_ids = tuple(row.id for row in affected_editorial)
    current_run_ids = set(
        session.scalars(
            select(EditorialContentState.current_run_id).where(
                EditorialContentState.owner_id == owner_id,
                EditorialContentState.current_run_id.in_(affected_run_ids),
            )
        )
    )
    quote_dependent_versions = tuple(
        {
            row.content_version_id
            for row in affected_editorial
            if row.id in current_run_ids and row.content_version_id not in content_version_ids
        }
    )
    session.execute(
        delete(EditorialContentState).where(
            EditorialContentState.owner_id == owner_id,
            EditorialContentState.current_run_id.in_(affected_run_ids),
        )
    )
    session.execute(
        delete(EditorialOverride).where(
            EditorialOverride.owner_id == owner_id,
            EditorialOverride.run_id.in_(affected_run_ids),
        )
    )
    session.execute(
        delete(EditorialRun).where(
            EditorialRun.owner_id == owner_id,
            EditorialRun.id.in_(affected_run_ids),
        )
    )
    if quote_dependent_versions:
        from events.content_cleanup import purge_event_content_inputs_in_transaction
        from publication.content_cleanup import purge_publication_content_inputs_in_transaction

        # Removing a quoted input invalidates its derived story, while the independently
        # lawful main raw version remains available for a new analysis configuration.
        purge_publication_content_inputs_in_transaction(
            session,
            owner_id=owner_id,
            content_version_ids=(),
            observation_ids=observation_ids,
            legacy_content_version_ids=quote_dependent_versions,
            now=now,
        )
        purge_event_content_inputs_in_transaction(
            session,
            owner_id=owner_id,
            content_version_ids=(),
            observation_ids=observation_ids,
            content_ids=(),
            legacy_content_version_ids=quote_dependent_versions,
            now=now,
        )
    runs = tuple(
        row.id
        for row in session.scalars(
            select(ContentTranslationRun).where(ContentTranslationRun.owner_id == owner_id)
        )
        if row.content_version_id in content_version_ids
        or uses(row.reference)
        or (
            row.content_version_id in legacy_content_version_ids
            and not row.reference.get("observation_id")
        )
    )
    session.execute(
        delete(ContentTranslationBatch).where(
            ContentTranslationBatch.owner_id == owner_id,
            ContentTranslationBatch.run_id.in_(runs),
        )
    )
    session.execute(
        delete(ContentTranslationRun).where(
            ContentTranslationRun.owner_id == owner_id,
            ContentTranslationRun.id.in_(runs),
        )
    )
