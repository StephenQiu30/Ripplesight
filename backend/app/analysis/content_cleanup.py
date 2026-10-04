"""Analysis-owned physical cleanup for content lifecycle, inside its original transaction."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from analysis.editorial_models import EditorialContentState, EditorialOverride, EditorialRun
from analysis.translation_models import ContentTranslationBatch, ContentTranslationRun


def purge_analysis_content_inputs_in_transaction(
    session: Session, *, owner_id: UUID, content_version_ids: tuple[UUID, ...], now: datetime
) -> None:
    if not session.in_transaction():
        raise RuntimeError("analysis cleanup requires caller transaction")
    affected_editorial = tuple(
        session.scalars(
            select(EditorialRun)
            .where(
                EditorialRun.owner_id == owner_id,
                or_(
                    EditorialRun.content_version_id.in_(content_version_ids),
                    EditorialRun.input_manifest["quote"]["content_version_id"].astext.in_(
                        tuple(str(i) for i in content_version_ids)
                    ),
                ),
            )
            .with_for_update()
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
            content_version_ids=quote_dependent_versions,
            now=now,
        )
        purge_event_content_inputs_in_transaction(
            session,
            owner_id=owner_id,
            content_version_ids=quote_dependent_versions,
            content_ids=(),
            now=now,
        )
    runs = tuple(
        session.scalars(
            select(ContentTranslationRun.id).where(
                ContentTranslationRun.owner_id == owner_id,
                ContentTranslationRun.content_version_id.in_(content_version_ids),
            )
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
