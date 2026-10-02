"""Leaderboard-owned evidence and published-run ledger. No automatic DDL."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class LeaderboardModel(Base):
    __tablename__ = "leaderboard_models"
    __table_args__ = (UniqueConstraint("slug", name="leaderboard_models_slug_key"),)

    id: Mapped[UUID] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(160))
    name: Mapped[str] = mapped_column(String(300))
    provider: Mapped[str | None] = mapped_column(String(160))
    provider_slug: Mapped[str | None] = mapped_column(String(100))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    release_date_source: Mapped[str | None] = mapped_column(String(100))
    metadata_source: Mapped[str] = mapped_column(String(100))
    context_window_tokens: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LeaderboardAlias(Base):
    __tablename__ = "leaderboard_aliases"
    __table_args__ = (
        UniqueConstraint("source_key", "alias", name="leaderboard_aliases_source_alias_key"),
        Index("leaderboard_aliases_model_idx", "model_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    source_key: Mapped[str] = mapped_column(String(100))
    alias: Mapped[str] = mapped_column(String(600))
    normalized_alias: Mapped[str] = mapped_column(String(160))
    model_id: Mapped[UUID] = mapped_column(ForeignKey("leaderboard_models.id"))


class LeaderboardSnapshot(Base):
    __tablename__ = "leaderboard_snapshots"
    __table_args__ = (
        CheckConstraint("record_count >= 0", name="leaderboard_snapshots_count_check"),
        Index("leaderboard_snapshots_source_fetched_idx", "source_key", "fetched_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    source_key: Mapped[str] = mapped_column(String(100))
    source_name: Mapped[str] = mapped_column(String(300))
    source_url: Mapped[str] = mapped_column(Text)
    license: Mapped[str] = mapped_column(Text)
    attribution_url: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    record_count: Mapped[int] = mapped_column(Integer)
    data: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB)


class LeaderboardScore(Base):
    __tablename__ = "leaderboard_scores"
    __table_args__ = (
        UniqueConstraint(
            "snapshot_id",
            "configuration_key",
            "metric_key",
            name="leaderboard_scores_config_metric_key",
        ),
        Index("leaderboard_scores_model_snapshot_idx", "model_id", "snapshot_id"),
        CheckConstraint(
            "configuration_kind IN ('FIRST_PARTY', 'SOURCE_DEFAULT', 'SCAFFOLDED')",
            name="leaderboard_scores_kind_check",
        ),
        CheckConstraint(
            "sample_size IS NULL OR sample_size >= 0", name="leaderboard_scores_sample_size_check"
        ),
        CheckConstraint(
            "lower_bound IS NULL OR upper_bound IS NULL OR lower_bound <= upper_bound",
            name="leaderboard_scores_bounds_check",
        ),
        Index("leaderboard_scores_snapshot_selected_idx", "snapshot_id", "selected_for_product"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("leaderboard_snapshots.id", ondelete="CASCADE")
    )
    model_id: Mapped[UUID] = mapped_column(ForeignKey("leaderboard_models.id"))
    configuration_key: Mapped[str] = mapped_column(String(800))
    configuration_label: Mapped[str] = mapped_column(String(400))
    configuration_kind: Mapped[str] = mapped_column(String(20))
    configuration_priority: Mapped[int] = mapped_column(Integer)
    selected_for_product: Mapped[bool] = mapped_column(Boolean)
    selection_reason: Mapped[str] = mapped_column(Text)
    metric_key: Mapped[str] = mapped_column(String(160))
    metric_name: Mapped[str] = mapped_column(String(300))
    raw_score: Mapped[float] = mapped_column(Float)
    lower_bound: Mapped[float | None] = mapped_column(Float)
    upper_bound: Mapped[float | None] = mapped_column(Float)
    source_rank: Mapped[int | None] = mapped_column(Integer)
    sample_size: Mapped[int | None] = mapped_column(Integer)
    source_model_name: Mapped[str] = mapped_column(String(600))
    source_organization: Mapped[str | None] = mapped_column(String(200))
    source_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    data: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB)


class LeaderboardRun(Base):
    __tablename__ = "leaderboard_runs"
    __table_args__ = (
        CheckConstraint("status IN ('published', 'failed')", name="leaderboard_runs_status_check"),
        CheckConstraint(
            "origin IN ('computed', 'refreshed')", name="leaderboard_runs_origin_check"
        ),
        Index("leaderboard_runs_status_generated_idx", "status", "generated_at", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    methodology_version: Mapped[str] = mapped_column(String(100))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_snapshot_ids: Mapped[list[str]] = mapped_column(JSONB)
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20))
    origin: Mapped[str] = mapped_column(String(20))
    fingerprint: Mapped[str] = mapped_column(String(64))
    failure_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LeaderboardRanking(Base):
    __tablename__ = "leaderboard_rankings"
    __table_args__ = (
        UniqueConstraint("run_id", "board", "model_id", name="leaderboard_rankings_model_key"),
        UniqueConstraint("run_id", "board", "rank", name="leaderboard_rankings_rank_key"),
        CheckConstraint("rank >= 1", name="leaderboard_rankings_rank_check"),
        CheckConstraint("score >= 0 AND score <= 100", name="leaderboard_rankings_score_check"),
        CheckConstraint(
            "coverage >= 0 AND metric_count >= 0", name="leaderboard_rankings_coverage_check"
        ),
        Index("leaderboard_rankings_model_run_idx", "model_id", "run_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("leaderboard_runs.id", ondelete="CASCADE"))
    board: Mapped[str] = mapped_column(String(40))
    model_id: Mapped[UUID] = mapped_column(ForeignKey("leaderboard_models.id"))
    rank: Mapped[int] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(Float)
    coverage: Mapped[float] = mapped_column(Float)
    metric_count: Mapped[int] = mapped_column(Integer)
    summary: Mapped[str] = mapped_column(Text)
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB)


class LeaderboardPrice(Base):
    __tablename__ = "leaderboard_prices"
    __table_args__ = (
        UniqueConstraint("model_id", "kind", name="leaderboard_prices_model_kind_key"),
        CheckConstraint("kind = 'official'", name="leaderboard_prices_kind_check"),
        CheckConstraint(
            "input_price IS NULL OR input_price >= 0", name="leaderboard_prices_input_check"
        ),
        CheckConstraint(
            "output_price IS NULL OR output_price >= 0", name="leaderboard_prices_output_check"
        ),
        CheckConstraint(
            "cached_input_price IS NULL OR cached_input_price >= 0",
            name="leaderboard_prices_cached_check",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    model_id: Mapped[UUID] = mapped_column(ForeignKey("leaderboard_models.id"))
    kind: Mapped[str] = mapped_column(String(30))
    currency: Mapped[str] = mapped_column(String(3))
    input_price: Mapped[float | None] = mapped_column(Float)
    output_price: Mapped[float | None] = mapped_column(Float)
    cached_input_price: Mapped[float | None] = mapped_column(Float)
    source_url: Mapped[str] = mapped_column(Text)
    verified_on: Mapped[date] = mapped_column(Date)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LeaderboardFxRate(Base):
    __tablename__ = "leaderboard_fx_rates"
    __table_args__ = (
        UniqueConstraint("pair", "as_of", name="leaderboard_fx_rates_pair_date_key"),
        CheckConstraint("pair = 'USD/CNY' AND rate > 0", name="leaderboard_fx_rates_rate_check"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    pair: Mapped[str] = mapped_column(String(10))
    as_of: Mapped[date] = mapped_column(Date)
    rate: Mapped[float] = mapped_column(Float)
    source_name: Mapped[str] = mapped_column(String(200))
    source_url: Mapped[str | None] = mapped_column(Text)


class LeaderboardSourceState(Base):
    __tablename__ = "leaderboard_source_states"
    __table_args__ = (
        CheckConstraint("request_count >= 0", name="leaderboard_source_states_requests_check"),
        CheckConstraint(
            "row_count IS NULL OR row_count >= 0", name="leaderboard_source_states_rows_check"
        ),
    )

    source_key: Mapped[str] = mapped_column(String(100), primary_key=True)
    ok: Mapped[bool] = mapped_column(Boolean)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_ok_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    changed: Mapped[bool | None] = mapped_column(Boolean)
    row_count: Mapped[int | None] = mapped_column(Integer)
    new_models: Mapped[int | None] = mapped_column(Integer)
    request_count: Mapped[int] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(100))
