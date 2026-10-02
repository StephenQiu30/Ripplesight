from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class SiteConfiguration(Base):
    __tablename__ = "operations_site_configurations"
    __table_args__ = (
        CheckConstraint("revision>=1", name="operations_site_configurations_revision_check"),
        CheckConstraint(
            "(wechat_qr_data IS NULL AND wechat_qr_sha256 IS NULL AND wechat_qr_mime IS NULL) OR "
            "(wechat_qr_data IS NOT NULL AND wechat_qr_sha256 IS NOT NULL "
            "AND wechat_qr_mime='image/png' "
            "AND octet_length(wechat_qr_data) BETWEEN 1 AND 2097152 "
            "AND octet_length(wechat_qr_sha256)=32)",
            name="operations_site_configurations_wechat_image_check",
        ),
        CheckConstraint(
            "(feishu_qr_data IS NULL AND feishu_qr_sha256 IS NULL AND feishu_qr_mime IS NULL) OR "
            "(feishu_qr_data IS NOT NULL AND feishu_qr_sha256 IS NOT NULL "
            "AND feishu_qr_mime='image/png' "
            "AND octet_length(feishu_qr_data) BETWEEN 1 AND 2097152 "
            "AND octet_length(feishu_qr_sha256)=32)",
            name="operations_site_configurations_feishu_image_check",
        ),
    )
    owner_id: Mapped[UUID] = mapped_column(primary_key=True)
    revision: Mapped[int]
    contact_enabled: Mapped[bool]
    contact_title: Mapped[str] = mapped_column(String(100))
    contact_text: Mapped[str] = mapped_column(String(4000))
    contact_url: Mapped[str | None] = mapped_column(String(1000))
    wechat_qr_data: Mapped[bytes | None] = mapped_column(LargeBinary)
    wechat_qr_sha256: Mapped[bytes | None] = mapped_column(LargeBinary(32))
    wechat_qr_mime: Mapped[str | None] = mapped_column(String(32))
    feishu_qr_data: Mapped[bytes | None] = mapped_column(LargeBinary)
    feishu_qr_sha256: Mapped[bytes | None] = mapped_column(LargeBinary(32))
    feishu_qr_mime: Mapped[str | None] = mapped_column(String(32))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
