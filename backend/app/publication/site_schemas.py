from datetime import datetime

from core.schemas import OutputModel


class PublicSiteStatisticsView(OutputModel):
    visible_items: int
    selected_items: int
    visible_sources: int
    latest_publication_at: datetime | None
    snapshot_at: datetime
