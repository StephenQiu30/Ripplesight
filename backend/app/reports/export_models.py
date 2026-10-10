"""Private export records; canonical sql/schema.sql alone creates these tables."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    LargeBinary,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import Constraint

from db.base import Base


class ExportColumns:
    id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID]
    operation_id: Mapped[UUID]
    job_id: Mapped[UUID]
    format: Mapped[str] = mapped_column(String(16))
    renderer_version: Mapped[str] = mapped_column(String(64))
    schema_version: Mapped[str] = mapped_column(String(32))
    input_manifest: Mapped[dict[str, object]] = mapped_column(JSONB)
    input_hash: Mapped[bytes] = mapped_column(LargeBinary)
    request_hash: Mapped[bytes] = mapped_column(LargeBinary)
    status: Mapped[str] = mapped_column(String(16))
    object_name: Mapped[str | None] = mapped_column(String(512))
    object_sha256: Mapped[bytes | None] = mapped_column(LargeBinary)
    object_size: Mapped[int | None] = mapped_column(BigInteger)
    mime_type: Mapped[str | None] = mapped_column(String(128))
    failure_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def constraints(prefix: str) -> tuple[Constraint, ...]:
    return (
        UniqueConstraint("owner_id", "id", name=f"{prefix}_owner_id_key"),
        UniqueConstraint("owner_id", "operation_id", name=f"{prefix}_operation_key"),
        ForeignKeyConstraint(
            ["owner_id", "job_id"], ["jobs.owner_id", "jobs.id"], name=f"{prefix}_job_fkey"
        ),
        CheckConstraint("format IN ('markdown','pdf','csv','json')", name=f"{prefix}_format_check"),
        CheckConstraint(
            "status IN ('pending','running','succeeded','failed','blocked','cancelled')",
            name=f"{prefix}_status_check",
        ),
        CheckConstraint(
            "jsonb_typeof(input_manifest)='object' AND octet_length(input_hash)=32 "
            "AND octet_length(request_hash)=32",
            name=f"{prefix}_input_check",
        ),
        CheckConstraint(
            "object_size IS NULL OR object_size BETWEEN 1 AND 5242880", name=f"{prefix}_size_check"
        ),
        CheckConstraint(
            "object_sha256 IS NULL OR octet_length(object_sha256)=32", name=f"{prefix}_hash_check"
        ),
        CheckConstraint(
            "(status='succeeded' AND object_name IS NOT NULL AND object_sha256 IS NOT NULL "
            "AND object_size IS NOT NULL AND mime_type IS NOT NULL) OR "
            "(status<>'succeeded' AND object_name IS NULL AND object_sha256 IS NULL "
            "AND object_size IS NULL AND mime_type IS NULL)",
            name=f"{prefix}_artifact_check",
        ),
    )


class ReportExport(ExportColumns, Base):
    __tablename__ = "report_exports"
    __table_args__ = (
        *constraints("report_exports"),
        Index(
            "report_exports_result_key",
            "owner_id",
            "report_id",
            "report_version",
            "format",
            "renderer_version",
            unique=True,
            postgresql_where=text("status <> 'cancelled'"),
        ),
        CheckConstraint("report_version>=1", name="report_exports_version_check"),
        ForeignKeyConstraint(
            ["owner_id", "report_id"],
            ["reports.owner_id", "reports.id"],
            name="report_exports_report_fkey",
            ondelete="CASCADE",
        ),
    )
    report_id: Mapped[UUID]
    report_version: Mapped[int]


class ContentExportRequest(ExportColumns, Base):
    __tablename__ = "content_export_requests"
    __table_args__ = (
        *constraints("content_export_requests"),
        Index(
            "content_exports_result_key",
            "owner_id",
            "input_hash",
            "format",
            "renderer_version",
            "schema_version",
            unique=True,
            postgresql_where=text("status <> 'cancelled'"),
        ),
    )
