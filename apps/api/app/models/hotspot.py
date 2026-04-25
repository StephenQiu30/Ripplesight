from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.app.db.base import Base

if TYPE_CHECKING:
    from apps.api.app.models.ai_analysis import AiAnalysis
    from apps.api.app.models.keyword import Keyword
    from apps.api.app.models.notification import Notification
    from apps.api.app.models.source import Source


class Hotspot(Base):
    __tablename__ = "hotspots"
    __table_args__ = (UniqueConstraint("source_id", "url", name="uq_hotspots_source_url"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False)
    keyword_id: Mapped[int | None] = mapped_column(ForeignKey("keywords.id", ondelete="SET NULL"))
    author: Mapped[str | None] = mapped_column(Text)
    snippet: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="new")
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    source: Mapped[Source] = relationship(back_populates="hotspots")
    keyword: Mapped[Keyword | None] = relationship(back_populates="hotspots")
    ai_analysis: Mapped[AiAnalysis | None] = relationship(back_populates="hotspot", uselist=False)
    notifications: Mapped[list[Notification]] = relationship(back_populates="hotspot")
