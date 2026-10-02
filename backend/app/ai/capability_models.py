"""One append-only capability configuration history; calls retain the original AiCall ledger."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Integer, LargeBinary, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class AiCapabilityConfiguration(Base):
    __tablename__ = "ai_capability_configurations"
    __table_args__ = (
        UniqueConstraint(
            "owner_id", "operation_id", name="ai_capability_configurations_owner_operation_key"
        ),
        CheckConstraint("version >= 1", name="ai_capability_configurations_version_check"),
        CheckConstraint(
            "octet_length(input_hash) = 32", name="ai_capability_configurations_hash_check"
        ),
        CheckConstraint(
            "jsonb_typeof(overrides) = 'object' AND octet_length(overrides::text) <= 4096",
            name="ai_capability_configurations_overrides_check",
        ),
    )
    owner_id: Mapped[UUID] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    operation_id: Mapped[UUID]
    input_hash: Mapped[bytes] = mapped_column(LargeBinary(32))
    overrides: Mapped[dict[str, str]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
