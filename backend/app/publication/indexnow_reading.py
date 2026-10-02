from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from events.reads import list_story_indexing_changes_in_transaction
from publication.indexnow_schemas import (
    IndexableChangeCursor,
    IndexableChangesView,
    canonical_indexnow_path,
)
from publication.publication_models import PublicationRecord, PublicationRevision
from publication.reading import PublicationReadingService
from publication.schemas import ProjectionView
from publication.services import require_transaction
from publication.stories import public_stories_in_transaction
from reports.edition_reading import (
    list_edition_indexing_changes_in_transaction,
    load_current_edition_in_transaction,
)
from reports.edition_rules import EditionKind
from reports.edition_schemas import EditionDetailView


def _edition_indexable(
    reader: PublicationReadingService, owner_id: UUID, view: EditionDetailView | None, now: datetime
) -> bool:
    if view is None or not view.valid or not view.content or not view.content.entries:
        return False
    identities = [entry.content_id for entry in view.content.entries]
    rows = list(
        reader.session.scalars(
            select(PublicationRecord).where(
                PublicationRecord.owner_id == owner_id, PublicationRecord.content_id.in_(identities)
            )
        )
    )
    live = reader._live(owner_id=owner_id, rows=rows, now=now)
    return all(identity in live and live[identity][0].indexable for identity in identities)


def load_indexable_changes_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    after: IndexableChangeCursor,
    until: datetime,
    limit: int = 500,
) -> IndexableChangesView:
    """Advance over a fixed revision page, including withdrawn canonical URLs."""
    require_transaction(session)
    if after.changed_at.utcoffset() is None or until.utcoffset() is None or not 1 <= limit <= 500:
        raise ValueError("IndexNow page requires aware dates and a bounded limit")
    revisions = list(
        session.scalars(
            select(PublicationRevision)
            .where(
                PublicationRevision.owner_id == owner_id,
                PublicationRevision.created_at <= until,
                tuple_(
                    PublicationRevision.created_at,
                    PublicationRevision.content_id,
                    PublicationRevision.revision,
                )
                > (after.changed_at, after.content_id, after.revision),
            )
            .order_by(
                PublicationRevision.created_at,
                PublicationRevision.content_id,
                PublicationRevision.revision,
            )
            .limit(limit)
        )
    )
    ids = {revision.content_id for revision in revisions}
    records = list(
        session.scalars(
            select(PublicationRecord).where(
                PublicationRecord.owner_id == owner_id, PublicationRecord.content_id.in_(ids)
            )
        )
    )
    reader = PublicationReadingService(session, indexing_enabled=True)
    live = reader._live(owner_id=owner_id, rows=records, now=until)
    paths: set[str] = set()
    for revision in revisions:
        current = live.get(revision.content_id)
        if current is not None:
            item = current[0]
            if item.indexable and item.visibility == "public" and item.eligible:
                if not item.selected or (
                    item.visible_after is not None and item.visible_after <= until
                ):
                    paths.add(f"/items/{item.content_id}")
            elif ProjectionView.model_validate(revision.data).indexable:
                # Only the canonical ID path is disclosed for removal; no withdrawn text.
                paths.add(f"/items/{revision.content_id}")
        elif ProjectionView.model_validate(revision.data).indexable:
            paths.add(f"/items/{revision.content_id}")
    edition_after = (after.edition_changed_at or after.changed_at, after.edition_id or UUID(int=0))
    editions = list_edition_indexing_changes_in_transaction(
        session, owner_id=owner_id, after=edition_after, until=until, limit=limit
    )
    for edition in editions:
        if edition.public and _edition_indexable(
            reader,
            owner_id,
            load_current_edition_in_transaction(
                session, owner_id=owner_id, kind=edition.kind, key=edition.key, now=until
            ),
            until,
        ):
            paths.add(f"/reports/{edition.kind}/{edition.key}")
    story_after = (after.story_changed_at or after.changed_at, after.story_id or UUID(int=0))
    story_changes = list_story_indexing_changes_in_transaction(
        session, owner_id=owner_id, after=story_after, until=until, limit=limit
    )
    story_ids = tuple(change.event_id for change in story_changes if change.eligible_story)
    for offset in range(0, len(story_ids), 100):
        for story in public_stories_in_transaction(
            reader, owner_id=owner_id, event_ids=story_ids[offset : offset + 100], now=until
        ):
            if story.indexable:
                paths.add(f"/discover/stories/{story.id}")
    last = revisions[-1] if revisions else None
    return IndexableChangesView(
        paths=sorted(paths),
        examined=len(revisions) + len(editions) + len(story_changes),
        next_cursor=IndexableChangeCursor(
            changed_at=last.created_at if last else after.changed_at,
            content_id=last.content_id if last else after.content_id,
            revision=last.revision if last else after.revision,
            edition_changed_at=editions[-1].changed_at if editions else edition_after[0],
            edition_id=editions[-1].edition_id if editions else edition_after[1],
            story_changed_at=story_changes[-1].changed_at if story_changes else story_after[0],
            story_id=story_changes[-1].event_id if story_changes else story_after[1],
        ),
    )


def revalidate_indexable_paths_in_transaction(
    session: Session, *, owner_id: UUID, paths: list[str], now: datetime
) -> list[str]:
    """Recheck all frozen IDs and avoid publishing any external URL or private metadata."""
    require_transaction(session)
    if len(paths) > 1500:
        raise ValueError("only bounded canonical internal paths are accepted")
    for path in paths:
        canonical_indexnow_path(path)
    ids = {UUID(path.removeprefix("/items/")) for path in paths if path.startswith("/items/")}
    records = list(
        session.scalars(
            select(PublicationRecord).where(
                PublicationRecord.owner_id == owner_id, PublicationRecord.content_id.in_(ids)
            )
        )
    )
    live = PublicationReadingService(session, indexing_enabled=True)._live(
        owner_id=owner_id, rows=records, now=now
    )
    result = []
    for record in records:
        item = live.get(record.content_id)
        # A disappearance still needs a removal notification. The frozen URL is our
        # own canonical ID, and the HTTP reader remains authoritative for 404/noindex.
        if (
            item is None
            or not item[0].indexable
            or not item[0].eligible
            or not item[0].selected
            or (item[0].visible_after is not None and item[0].visible_after <= now)
        ):
            result.append(f"/items/{record.content_id}")
    for path in paths:
        if not path.startswith("/items/"):
            # Only paths frozen by our admission from an indexable live report/story
            # reach this branch. Re-reading may now yield a removal, never body text.
            parts = path.split("/")
            if parts[1] == "reports":
                load_current_edition_in_transaction(
                    session,
                    owner_id=owner_id,
                    kind=cast(EditionKind, parts[2]),
                    key=parts[3],
                    now=now,
                )
            else:
                public_stories_in_transaction(
                    PublicationReadingService(session, indexing_enabled=True),
                    owner_id=owner_id,
                    event_ids=(UUID(parts[3]),),
                    now=now,
                )
            result.append(path)
    return sorted(set(result))


def read_indexable_path_eligibilities_in_transaction(
    session: Session, *, owner_id: UUID, paths: list[str], now: datetime
) -> dict[str, bool]:
    """Current eligibility only; accepted-path provenance stays in the operations receipt."""
    require_transaction(session)
    if now.utcoffset() is None or len(paths) > 1500:
        raise ValueError("eligibility requires an aware cutoff and at most 1500 canonical paths")
    for path in paths:
        canonical_indexnow_path(path)
    result = dict.fromkeys(paths, False)
    reader = PublicationReadingService(session, indexing_enabled=True)
    identities = {UUID(path.split("/")[2]) for path in paths if path.startswith("/items/")}
    ids = tuple(identities)
    for offset in range(0, len(ids), 500):
        rows = list(
            session.scalars(
                select(PublicationRecord).where(
                    PublicationRecord.owner_id == owner_id,
                    PublicationRecord.content_id.in_(ids[offset : offset + 500]),
                )
            )
        )
        live = reader._live(owner_id=owner_id, rows=rows, now=now)
        for content_id, (projection, _) in live.items():
            result[f"/items/{content_id}"] = (
                projection.indexable
                and projection.visibility == "public"
                and projection.eligible
                and (
                    not projection.selected
                    or (projection.visible_after is not None and projection.visible_after <= now)
                )
            )
    stories = tuple(
        {UUID(path.split("/")[3]) for path in paths if path.startswith("/discover/stories/")}
    )
    for offset in range(0, len(stories), 100):
        for story in public_stories_in_transaction(
            reader, owner_id=owner_id, event_ids=stories[offset : offset + 100], now=now
        ):
            result[f"/discover/stories/{story.id}"] = story.indexable
    for path in paths:
        if not path.startswith("/reports/"):
            continue
        _, _, kind, key = path.split("/")
        result[path] = _edition_indexable(
            reader,
            owner_id,
            load_current_edition_in_transaction(
                session, owner_id=owner_id, kind=cast(EditionKind, kind), key=key, now=now
            ),
            now,
        )
    return result
