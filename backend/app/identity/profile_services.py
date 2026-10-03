from __future__ import annotations

import base64
import binascii
import hashlib
import warnings
from datetime import UTC, datetime
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.errors import ApplicationError
from identity.models import IdentitySession, IdentityUser
from identity.profile_schemas import IdentityAvatarInput, IdentityProfileInput
from identity.schemas import IdentitySessionView
from identity.services import AuthenticatedIdentity, IdentityService

_FORMATS = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}


def normalize_avatar(command: IdentityAvatarInput) -> bytes:
    """Bound decoding, apply orientation, crop square, and discard original metadata."""
    try:
        raw = base64.b64decode(command.data_base64, validate=True)
        if not 1 <= len(raw) <= 2 * 1024 * 1024:
            raise ValueError("avatar exceeds byte limit")
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as source:
                if (
                    source.format != _FORMATS[command.mime]
                    or not 1 <= source.width <= 4096
                    or not 1 <= source.height <= 4096
                    or source.width * source.height > 4_000_000
                    or getattr(source, "n_frames", 1) != 1
                ):
                    raise ValueError("unsupported image")
                source.load()
                oriented = ImageOps.exif_transpose(source)
                square = ImageOps.fit(oriented.convert("RGB"), (256, 256), Image.Resampling.LANCZOS)
                # Create a clean image rather than copying EXIF/ICC from the original.
                clean = Image.new("RGB", square.size)
                clean.paste(square)
                output = BytesIO()
                clean.save(output, format="PNG", optimize=True)
                encoded = output.getvalue()
        if len(encoded) > 262144:
            raise ValueError("normalized avatar exceeds byte limit")
        return encoded
    except (
        ValueError,
        binascii.Error,
        OSError,
        UnidentifiedImageError,
        Image.DecompressionBombWarning,
        Image.DecompressionBombError,
    ):
        raise ApplicationError("invalid_avatar") from None


class IdentityProfileService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _active_user(self, identity: AuthenticatedIdentity) -> tuple[IdentityUser, IdentitySession]:
        # Same lock order as credential updates; recheck revocation inside the write transaction.
        user = self.session.get(
            IdentityUser, identity.view.user.id, with_for_update=True, populate_existing=True
        )
        active = self.session.get(
            IdentitySession, identity.session_id, with_for_update=True, populate_existing=True
        )
        if (
            user is None
            or active is None
            or active.user_id != user.id
            or active.revoked_at is not None
            or active.expires_at <= datetime.now(UTC)
            or active.credential_version != user.credential_version
        ):
            raise ApplicationError("invalid_session")
        return user, active

    def update_profile(
        self, identity: AuthenticatedIdentity, command: IdentityProfileInput
    ) -> IdentitySessionView:
        try:
            with self.session.begin():
                user, active = self._active_user(identity)
                user.username, user.updated_at = command.username, datetime.now(UTC)
                self.session.flush()
                return IdentityService._view(user, active.expires_at)
        except IntegrityError:
            raise ApplicationError("username_unavailable") from None

    def upload_avatar(
        self, identity: AuthenticatedIdentity, command: IdentityAvatarInput
    ) -> IdentitySessionView:
        encoded = normalize_avatar(command)
        with self.session.begin():
            user, active = self._active_user(identity)
            user.avatar_data, user.avatar_sha256 = encoded, hashlib.sha256(encoded).digest()
            user.updated_at = datetime.now(UTC)
            self.session.flush()
            return IdentityService._view(user, active.expires_at)

    def read_avatar(self, identity: AuthenticatedIdentity, sha256: str) -> bytes:
        with self.session.begin():
            user, _active = self._active_user(identity)
            if user.avatar_sha256 is None or user.avatar_sha256.hex() != sha256:
                raise ApplicationError("resource_not_found")
            body = user.avatar_data
            if body is None or hashlib.sha256(body).digest() != user.avatar_sha256:
                raise ApplicationError("resource_not_found")
            return bytes(body)
