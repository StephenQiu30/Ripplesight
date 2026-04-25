from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Numeric, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.app.db.base import Base

if TYPE_CHECKING:
    from apps.api.app.models.hotspot import Hotspot


class AiAnalysis(Base):
    __tablename__ = "ai_analyses"
    __table_args__ = (CheckConstraint("relevance_score >= 0 AND relevance_score <= 100", name="ck_ai_analyses_relevance_score"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    hotspot_id: Mapped[int] = mapped_column(ForeignKey("hotspots.id", ondelete="CASCADE"), unique=True, nullable=False)
    is_real: Mapped[bool | None] = mapped_column(Boolean)
    relevance_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, server_default="0")
    relevance_reason: Mapped[str | None] = mapped_column(Text)
    keyword_mentioned: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    importance: Mapped[str] = mapped_column(Text, nullable=False, server_default="medium")
    summary: Mapped[str | None] = mapped_column(Text)
    model_name: Mapped[str | None] = mapped_column(Text)
    raw_response: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    hotspot: Mapped[Hotspot] = relationship(back_populates="ai_analysis")
