from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, LargeBinary, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class IdentityUser(Base):
    __tablename__ = "identity_users"
    __table_args__ = (
        CheckConstraint("credential_version >= 1", name="identity_users_credential_version_check"),
        CheckConstraint(
            "(avatar_data IS NULL AND avatar_sha256 IS NULL) OR "
            "(avatar_data IS NOT NULL AND avatar_sha256 IS NOT NULL "
            "AND octet_length(avatar_data) BETWEEN 1 AND 262144 "
            "AND octet_length(avatar_sha256) = 32)",
            name="identity_users_avatar_check",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    email: Mapped[str | None] = mapped_column(String(254), unique=True)
    github_user_id: Mapped[str | None] = mapped_column(String(32), unique=True)
    password_hash: Mapped[str | None] = mapped_column(Text)
    avatar_data: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
    avatar_sha256: Mapped[bytes | None] = mapped_column(LargeBinary(32))
    credential_version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    sessions: Mapped[list[IdentitySession]] = relationship(back_populates="user")


class IdentitySession(Base):
    __tablename__ = "identity_sessions"
    __table_args__ = (
        CheckConstraint("octet_length(token_digest) = 32", name="identity_sessions_token_length"),
        CheckConstraint("octet_length(csrf_digest) = 32", name="identity_sessions_csrf_length"),
        CheckConstraint("credential_version >= 1", name="identity_sessions_credential_version"),
        CheckConstraint("expires_at > created_at", name="identity_sessions_expiry"),
        CheckConstraint(
            "(revoked_at IS NULL AND revoked_reason IS NULL) OR "
            "(revoked_at IS NOT NULL AND revoked_reason IS NOT NULL)",
            name="identity_sessions_revocation",
        ),
        Index("identity_sessions_user_id_idx", "user_id"),
        Index(
            "identity_sessions_active_expiry_idx",
            "expires_at",
            postgresql_where=text("revoked_at IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id", ondelete="CASCADE"))
    token_digest: Mapped[bytes] = mapped_column(LargeBinary(32), unique=True)
    csrf_digest: Mapped[bytes] = mapped_column(LargeBinary(32))
    credential_version: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(String(32))
    user: Mapped[IdentityUser] = relationship(back_populates="sessions")


class IdentityEmailChallenge(Base):
    """Latest email proof per bound flow; consumed with the identity transaction."""

    __tablename__ = "identity_email_challenges"
    __table_args__ = (
        CheckConstraint("octet_length(scope_digest) = 32", name="identity_email_scope_length"),
        CheckConstraint("octet_length(binding_digest) = 32", name="identity_email_binding_length"),
        CheckConstraint("octet_length(code_digest) = 32", name="identity_email_code_length"),
        CheckConstraint(
            "purpose IN ('login', 'email_link', 'credentials_update')",
            name="identity_email_purpose",
        ),
        CheckConstraint("attempt_count BETWEEN 0 AND 5", name="identity_email_attempts"),
        CheckConstraint("expires_at > created_at", name="identity_email_expiry"),
        CheckConstraint(
            "consumed_at IS NULL OR invalidated_at IS NULL", name="identity_email_terminal"
        ),
        Index("identity_email_expiry_idx", "expires_at"),
    )

    scope_digest: Mapped[bytes] = mapped_column(LargeBinary(32), primary_key=True)
    challenge_id: Mapped[UUID] = mapped_column(unique=True)
    email: Mapped[str] = mapped_column(String(254))
    purpose: Mapped[str] = mapped_column(String(24))
    binding_digest: Mapped[bytes] = mapped_column(LargeBinary(32))
    code_digest: Mapped[bytes] = mapped_column(LargeBinary(32))
    attempt_count: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
