from datetime import datetime
from typing import cast
from uuid import UUID

from core.schemas import OutputModel
from reports.edition_rules import EditionKind, period_window


class IndexableChangeCursor(OutputModel):
    changed_at: datetime
    content_id: UUID
    revision: int
    edition_changed_at: datetime | None = None
    edition_id: UUID | None = None
    story_changed_at: datetime | None = None
    story_id: UUID | None = None


class IndexableChangesView(OutputModel):
    paths: list[str]
    next_cursor: IndexableChangeCursor
    examined: int


def canonical_indexnow_path(value: str) -> str:
    parts = value.split("/")
    if len(parts) == 3 and parts[1] == "items":
        expected = f"/items/{UUID(parts[2])}"
    elif len(parts) == 4 and parts[1:3] == ["discover", "stories"]:
        expected = f"/discover/stories/{UUID(parts[3])}"
    elif len(parts) == 4 and parts[1] == "reports" and parts[2] in {"daily", "weekly", "monthly"}:
        period_window(cast(EditionKind, parts[2]), parts[3])
        expected = f"/reports/{parts[2]}/{parts[3]}"
    else:
        raise ValueError("unsupported internal IndexNow path")
    if value != expected:
        raise ValueError("noncanonical internal IndexNow path")
    return expected
