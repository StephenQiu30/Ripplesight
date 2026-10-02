from datetime import UTC, datetime
from html import escape
from uuid import UUID

from sqlalchemy.orm import Session

from core.errors import ApplicationError
from publication.listing import iter_current_publications_in_transaction
from publication.site_schemas import PublicSiteStatisticsView


class PublicSiteReadingService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def statistics(self, *, owner_id: UUID) -> PublicSiteStatisticsView:
        at = datetime.now(UTC)
        visible = selected = 0
        latest: datetime | None = None
        sources: set[str] = set()
        with self.session.begin():
            for member in iter_current_publications_in_transaction(
                self.session, owner_id=owner_id, now=at
            ):
                item = member.projection
                if item.selected and (item.visible_after is None or item.visible_after > at):
                    continue
                visible += 1
                selected += int(item.selected)
                sources.add(item.source_key)
                latest = max(latest, item.sort_at) if latest else item.sort_at
        return PublicSiteStatisticsView(
            visible_items=visible,
            selected_items=selected,
            visible_sources=len(sources),
            latest_publication_at=latest,
            snapshot_at=at,
        )

    def source_icon(self, *, owner_id: UUID, source_key: str) -> str:
        """Locally generated fallback for a currently public source; no URL proxy."""
        with self.session.begin():
            at = datetime.now(UTC)
            for member in iter_current_publications_in_transaction(
                self.session, owner_id=owner_id, now=at
            ):
                item = member.projection
                if item.selected and (item.visible_after is None or item.visible_after > at):
                    continue
                if member.projection.source_key == source_key:
                    initials = escape(member.projection.source_name[:2] or "HK")
                    return (
                        '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" '
                        'viewBox="0 0 64 64" role="img"><rect width="64" height="64" '
                        'rx="12" fill="#171717"/><text x="32" y="40" text-anchor="middle" '
                        f'font-family="sans-serif" font-size="22" fill="white">{initials}'
                        "</text></svg>"
                    )
        raise ApplicationError("resource_not_found")
