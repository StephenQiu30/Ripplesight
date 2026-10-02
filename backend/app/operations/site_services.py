from __future__ import annotations

import base64
import binascii
import hashlib
import warnings
from datetime import UTC, datetime
from io import BytesIO
from uuid import UUID

from PIL import Image, UnidentifiedImageError
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from core.config import Settings
from core.errors import ApplicationError
from operations.services import accept_audit_in_transaction, complete_audit_in_transaction
from operations.site_models import SiteConfiguration
from operations.site_schemas import (
    ContactImageInput,
    PublicContactView,
    PublicSiteFeatures,
    PublicSiteMetaView,
    SiteConfigurationInput,
    SiteConfigurationView,
)

_IMAGE_LIMIT = 2 * 1024 * 1024
_FORMATS = {"image/png": "PNG", "image/jpeg": "JPEG", "image/webp": "WEBP", "image/gif": "GIF"}


def normalize_contact_image(image: ContactImageInput) -> bytes:
    """Decode the complete image and discard metadata/animation, without external I/O."""
    try:
        raw = base64.b64decode(image.data_base64, validate=True)
        if not 1 <= len(raw) <= _IMAGE_LIMIT:
            raise ValueError("contact image exceeds the byte limit")
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as loaded:
                if (
                    loaded.format != _FORMATS[image.mime]
                    or not 1 <= loaded.width <= 4096
                    or not 1 <= loaded.height <= 4096
                    or loaded.width * loaded.height > 4_000_000
                ):
                    raise ValueError("contact image dimensions or MIME do not match")
                loaded.load()
                result = BytesIO()
                loaded.convert("RGBA").save(result, format="PNG", optimize=True)
                encoded = result.getvalue()
        if len(encoded) > _IMAGE_LIMIT:
            raise ValueError("normalized contact image exceeds the byte limit")
        return encoded
    except (
        ValueError,
        binascii.Error,
        OSError,
        UnidentifiedImageError,
        Image.DecompressionBombWarning,
        Image.DecompressionBombError,
    ) as error:
        raise ApplicationError("invalid_operations_input") from error


def _view(row: SiteConfiguration | None) -> SiteConfigurationView:
    if row is None:
        return SiteConfigurationView(
            revision=0,
            contact_enabled=False,
            contact_title="联系",
            contact_text="",
            contact_url=None,
            wechat_qr_url=None,
            feishu_qr_url=None,
            updated_at=None,
        )
    return SiteConfigurationView(
        revision=row.revision,
        contact_enabled=row.contact_enabled,
        contact_title=row.contact_title,
        contact_text=row.contact_text,
        contact_url=row.contact_url,
        wechat_qr_url=(
            f"/api/site/contact/qr/{row.wechat_qr_sha256.hex()}.png"
            if row.wechat_qr_sha256
            else None
        ),
        feishu_qr_url=(
            f"/api/site/contact/qr/{row.feishu_qr_sha256.hex()}.png"
            if row.feishu_qr_sha256
            else None
        ),
        updated_at=row.updated_at,
    )


class SiteConfigurationService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session, self.settings = session, settings

    def meta(self) -> PublicSiteMetaView:
        return PublicSiteMetaView(
            name=self.settings.app_name,
            version=self.settings.app_version,
            environment=self.settings.environment,
            description="按主题监控、追溯来源与事件进展,阅读经许可发布的精选资料。",
            public_base_url=self.settings.web_base_url.rstrip("/"),
            robots_index=self.settings.publication_indexing_enabled,
            features=PublicSiteFeatures(
                editorial_analysis=self.settings.ai_enabled,
                model_leaderboard=self.settings.leaderboard_enabled,
                codex_monitor=self.settings.codex_resets_enabled,
                notifications=self.settings.notifications_enabled,
                smtp=self.settings.notifications_enabled
                and self.settings.notification_smtp_enabled,
                media_mirror=self.settings.media_mirror_enabled,
                feedback=self.settings.feedback_hmac_secret is not None,
                external_indexing=self.settings.indexnow_enabled
                and self.settings.indexnow_external_requests_enabled
                and self.settings.publication_indexing_enabled,
            ),
        )

    def indexnow_verification(self) -> str:
        if not (
            self.settings.indexnow_enabled
            and self.settings.indexnow_external_requests_enabled
            and self.settings.publication_indexing_enabled
            and self.settings.indexnow_key
        ):
            raise ApplicationError("resource_not_found")
        return self.settings.indexnow_key.get_secret_value()

    def get(self, *, owner_id: UUID) -> SiteConfigurationView:
        with self.session.begin():
            return _view(self.session.get(SiteConfiguration, owner_id))

    def contact(self, *, owner_id: UUID | None) -> PublicContactView:
        if owner_id is None:
            return PublicContactView(
                enabled=False,
                title=None,
                text=None,
                url=None,
                wechat_qr_url=None,
                feishu_qr_url=None,
                revision=0,
            )
        value = self.get(owner_id=owner_id)
        return PublicContactView(
            enabled=value.contact_enabled,
            title=value.contact_title if value.contact_enabled else None,
            text=value.contact_text if value.contact_enabled else None,
            url=value.contact_url if value.contact_enabled else None,
            wechat_qr_url=value.wechat_qr_url if value.contact_enabled else None,
            feishu_qr_url=value.feishu_qr_url if value.contact_enabled else None,
            revision=value.revision,
        )

    def image(self, *, owner_id: UUID | None, sha256: str) -> bytes:
        if owner_id is None:
            raise ApplicationError("resource_not_found")
        with self.session.begin():
            row = self.session.get(SiteConfiguration, owner_id)
            if row is None or not row.contact_enabled:
                raise ApplicationError("resource_not_found")
            for data, digest in (
                (row.wechat_qr_data, row.wechat_qr_sha256),
                (row.feishu_qr_data, row.feishu_qr_sha256),
            ):
                if data is not None and digest is not None and digest.hex() == sha256:
                    return bytes(data)
            raise ApplicationError("resource_not_found")

    def save(
        self, *, owner_id: UUID, command: SiteConfigurationInput, now: datetime | None = None
    ) -> SiteConfigurationView:
        at = now or datetime.now(UTC)
        normalized = normalize_contact_image(command.wechat_image) if command.wechat_image else None
        feishu_normalized = (
            normalize_contact_image(command.feishu_image) if command.feishu_image else None
        )
        payload = command.model_dump(mode="json", exclude={"wechat_image", "feishu_image"})
        payload["image_sha256"] = hashlib.sha256(normalized).hexdigest() if normalized else None
        payload["feishu_image_sha256"] = (
            hashlib.sha256(feishu_normalized).hexdigest() if feishu_normalized else None
        )
        with self.session.begin():
            self.session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
                {"key": f"site-config:{owner_id}"},
            )
            row = self.session.scalar(
                select(SiteConfiguration)
                .where(SiteConfiguration.owner_id == owner_id)
                .with_for_update()
            )
            previous = _view(row)
            audit, replayed = accept_audit_in_transaction(
                self.session,
                owner_id=owner_id,
                operation_id=command.operation_id,
                action="site.configure",
                target_ref="site",
                reason=command.reason,
                payload=payload,
                before_state=previous.model_dump(mode="json"),
                now=at,
            )
            if replayed:
                return SiteConfigurationView.model_validate(audit.after_state)
            if previous.revision != command.expected_revision:
                raise ApplicationError("operations_revision_conflict")
            if row is None:
                row = SiteConfiguration(
                    owner_id=owner_id,
                    revision=1,
                    contact_enabled=False,
                    contact_title="联系",
                    contact_text="",
                    contact_url=None,
                    wechat_qr_data=None,
                    wechat_qr_sha256=None,
                    wechat_qr_mime=None,
                    feishu_qr_data=None,
                    feishu_qr_sha256=None,
                    feishu_qr_mime=None,
                    updated_at=at,
                )
                self.session.add(row)
            else:
                row.revision += 1
            row.contact_enabled = command.contact_enabled
            row.contact_title, row.contact_text = command.contact_title, command.contact_text
            row.contact_url, row.updated_at = command.contact_url, at
            if command.wechat_qr_action == "replace":
                assert normalized is not None
                row.wechat_qr_data, row.wechat_qr_sha256, row.wechat_qr_mime = (
                    normalized,
                    hashlib.sha256(normalized).digest(),
                    "image/png",
                )
            elif command.wechat_qr_action == "clear":
                row.wechat_qr_data = row.wechat_qr_sha256 = row.wechat_qr_mime = None
            if command.feishu_qr_action == "replace":
                assert feishu_normalized is not None
                row.feishu_qr_data, row.feishu_qr_sha256, row.feishu_qr_mime = (
                    feishu_normalized,
                    hashlib.sha256(feishu_normalized).digest(),
                    "image/png",
                )
            elif command.feishu_qr_action == "clear":
                row.feishu_qr_data = row.feishu_qr_sha256 = row.feishu_qr_mime = None
            self.session.flush()
            view = _view(row)
            complete_audit_in_transaction(
                self.session,
                owner_id=owner_id,
                operation_id=command.operation_id,
                after_state=view.model_dump(mode="json"),
                now=at,
            )
            return view
