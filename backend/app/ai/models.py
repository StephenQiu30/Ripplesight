from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class AiCall(Base):
    __tablename__ = "ai_calls"
    __table_args__ = (
        UniqueConstraint("owner_id", "id", name="ai_calls_owner_id_key"),
        ForeignKeyConstraint(
            ["owner_id", "job_id"],
            ["jobs.owner_id", "jobs.id"],
            name="ai_calls_owner_job_fkey",
        ),
        CheckConstraint(
            "status IN ('running', 'unknown', 'succeeded', 'failed')",
            name="ai_calls_status_check",
        ),
        CheckConstraint(
            "failure_code IS NULL OR failure_code IN "
            "('rate_limited', 'unavailable', 'timeout', 'invalid_output', "
            "'output_truncated', 'failed')",
            name="ai_calls_failure_code_check",
        ),
        CheckConstraint(
            "(status IN ('running', 'succeeded') AND failure_code IS NULL) OR "
            "(status IN ('unknown', 'failed') AND failure_code IS NOT NULL)",
            name="ai_calls_status_failure_check",
        ),
        CheckConstraint(
            "octet_length(input_fingerprint) = 32",
            name="ai_calls_fingerprint_length_check",
        ),
        CheckConstraint(
            "input_tokens >= 0 AND cached_input_tokens >= 0 AND output_tokens >= 0 "
            "AND reasoning_output_tokens >= 0",
            name="ai_calls_token_usage_check",
        ),
        CheckConstraint("duration_ms >= 0", name="ai_calls_duration_check"),
        CheckConstraint(
            "routing_version IS NULL OR routing_version >= 0", name="ai_calls_routing_version_check"
        ),
        CheckConstraint(
            "execution_epoch IS NULL OR execution_epoch >= 1",
            name="ai_calls_execution_epoch_check",
        ),
        CheckConstraint(
            "routing_hash IS NULL OR octet_length(routing_hash) = 32",
            name="ai_calls_routing_hash_check",
        ),
        CheckConstraint(
            "currency IS NULL OR currency IN ('USD', 'CNY')", name="ai_calls_currency_check"
        ),
        CheckConstraint(
            "(cost_estimate_micros IS NULL OR cost_estimate_micros >= 0) AND "
            "(cost_actual_micros IS NULL OR cost_actual_micros >= 0) AND "
            "(cost_cap_micros IS NULL OR cost_cap_micros >= 0)",
            name="ai_calls_cost_check",
        ),
        Index("ai_calls_owner_created_idx", "owner_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID] = mapped_column()
    job_id: Mapped[UUID | None]
    purpose: Mapped[str] = mapped_column(String(128))
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128))
    prompt_version: Mapped[str] = mapped_column(String(128))
    input_fingerprint: Mapped[bytes] = mapped_column(LargeBinary(32))
    status: Mapped[str] = mapped_column(String(16))
    failure_code: Mapped[str | None] = mapped_column(String(32))
    input_tokens: Mapped[int] = mapped_column(BigInteger)
    cached_input_tokens: Mapped[int] = mapped_column(BigInteger)
    output_tokens: Mapped[int] = mapped_column(BigInteger)
    reasoning_output_tokens: Mapped[int] = mapped_column(BigInteger)
    duration_ms: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime]

    model_key: Mapped[str | None] = mapped_column(String(64), default=None)
    routing_version: Mapped[int | None] = mapped_column(BigInteger, default=None)
    routing_hash: Mapped[bytes | None] = mapped_column(LargeBinary(32), default=None)
    currency: Mapped[str | None] = mapped_column(String(3), default=None)
    cost_estimate_micros: Mapped[int | None] = mapped_column(BigInteger, default=None)
    cost_actual_micros: Mapped[int | None] = mapped_column(BigInteger, default=None)
    cost_cap_micros: Mapped[int | None] = mapped_column(BigInteger, default=None)
    execution_epoch: Mapped[int | None] = mapped_column(BigInteger, default=None)
