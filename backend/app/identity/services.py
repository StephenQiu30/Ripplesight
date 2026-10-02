from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import unquote, urlsplit
from uuid import UUID, uuid4

from pwdlib import PasswordHash
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from core.config import Settings
from core.errors import ApplicationError
from identity.adapters.email import SmtpEmailAdapter
from identity.adapters.github import GitHubAdapter
from identity.adapters.verification_store import VerificationStore
from identity.models import IdentitySession, IdentityUser
from identity.schemas import (
    EmailChallengeView,
    IdentityCredentialsUpdateInput,
    IdentitySessionView,
    IdentityUserView,
    LoginOptionsView,
)

_PASSWORD_HASH = PasswordHash.recommended()
_DUMMY_PASSWORD_HASH = _PASSWORD_HASH.hash(secrets.token_urlsafe(32))


def token_digest(value: str) -> bytes:
    return hashlib.sha256(value.encode()).digest()


def safe_return_to(value: str) -> str:
    decoded = unquote(value)
    try:
        parsed = urlsplit(decoded)
    except ValueError:
        return "/topics"
    if (
        not decoded.startswith("/")
        or decoded.startswith("//")
        or "\\" in decoded
        or any(ord(character) < 32 or ord(character) == 127 for character in decoded)
        or parsed.netloc
        or parsed.scheme
        or parsed.path in {"/", "/login", "/register"}
        or parsed.path.startswith(("/api/", "/_next/"))
    ):
        return "/topics"
    return value


@dataclass(frozen=True, slots=True)
class CreatedIdentitySession:
    view: IdentitySessionView
    session_token: str
    csrf_token: str


@dataclass(frozen=True, slots=True)
class AuthenticatedIdentity:
    session_id: UUID
    view: IdentitySessionView
    csrf_digest: bytes
    created_at: datetime


class IdentityService:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        *,
        verification: VerificationStore | None = None,
        github: GitHubAdapter | None = None,
        email: SmtpEmailAdapter | None = None,
    ) -> None:
        self.session, self.settings = session, settings
        self.verification, self.github, self.email = verification, github, email

    @property
    def cookie_secure(self) -> bool:
        return self.settings.environment in {"staging", "production"}

    def options(self) -> LoginOptionsView:
        return LoginOptionsView(
            password=True,
            github=bool(self.settings.github_client_id),
            email=bool(self.settings.auth_smtp_host),
        )

    def _store(self) -> VerificationStore:
        if self.verification is None:
            raise ApplicationError("auth_dependency_unavailable")
        return self.verification

    @staticmethod
    def _view(user: IdentityUser, expires_at: datetime) -> IdentitySessionView:
        return IdentitySessionView(
            user=IdentityUserView(id=user.id, username=user.username, email=user.email),
            expires_at=expires_at,
        )

    def _new_session(self, user: IdentityUser, now: datetime) -> CreatedIdentitySession:
        session_token, csrf_token = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        expires = now + timedelta(seconds=self.settings.session_ttl_seconds)
        self.session.add(
            IdentitySession(
                id=uuid4(),
                user_id=user.id,
                token_digest=token_digest(session_token),
                csrf_digest=token_digest(csrf_token),
                credential_version=user.credential_version,
                created_at=now,
                expires_at=expires,
                revoked_at=None,
                revoked_reason=None,
            )
        )
        self.session.flush()
        return CreatedIdentitySession(self._view(user, expires), session_token, csrf_token)

    def login(self, *, username: str, password: str, client_ip: str) -> CreatedIdentitySession:
        username = username.lower()
        self._store().limit_password(username, client_ip)
        now = datetime.now(UTC)
        with self.session.begin():
            user = self.session.scalar(
                select(IdentityUser).where(IdentityUser.username == username).with_for_update()
            )
            stored = user.password_hash if user and user.password_hash else _DUMMY_PASSWORD_HASH
            valid, replacement = _PASSWORD_HASH.verify_and_update(password, stored)
            if user is None or user.password_hash is None or not valid:
                raise ApplicationError("invalid_credentials")
            if replacement:
                user.password_hash, user.updated_at = replacement, now
            return self._new_session(user, now)

    def authenticate(self, token: str | None) -> AuthenticatedIdentity:
        if token is None or not 32 <= len(token) <= 128:
            raise ApplicationError("invalid_session")
        with self.session.begin():
            model = self.session.scalar(
                select(IdentitySession)
                .options(joinedload(IdentitySession.user))
                .where(IdentitySession.token_digest == token_digest(token))
            )
            now = datetime.now(UTC)
            if (
                model is None
                or model.revoked_at is not None
                or model.expires_at <= now
                or model.credential_version != model.user.credential_version
            ):
                raise ApplicationError("invalid_session")
            return AuthenticatedIdentity(
                model.id,
                self._view(model.user, model.expires_at),
                bytes(model.csrf_digest),
                model.created_at,
            )

    @staticmethod
    def validate_csrf(
        identity: AuthenticatedIdentity, *, cookie: str | None, header: str | None
    ) -> None:
        if (
            cookie is None
            or header is None
            or not 32 <= len(header) <= 128
            or not cookie.isascii()
            or not header.isascii()
            or not secrets.compare_digest(cookie, header)
            or not secrets.compare_digest(token_digest(header), identity.csrf_digest)
        ):
            raise ApplicationError("csrf_invalid")

    def logout(self, identity: AuthenticatedIdentity) -> None:
        with self.session.begin():
            model = self.session.get(IdentitySession, identity.session_id, with_for_update=True)
            if model is None or model.user_id != identity.view.user.id:
                raise ApplicationError("invalid_session")
            model.revoked_at, model.revoked_reason = datetime.now(UTC), "logout"

    def send_email_code(
        self, *, email: str, client_ip: str, identity: AuthenticatedIdentity | None = None
    ) -> EmailChallengeView:
        if not self.options().email or self.email is None:
            raise ApplicationError("email_login_unavailable")
        if identity is not None and identity.view.user.email != email:
            raise ApplicationError("invalid_email_code")
        challenge = self._store().send_email_challenge(
            email,
            client_ip,
            purpose="credentials_update" if identity else "login",
            user_id=str(identity.view.user.id) if identity else None,
        )
        try:
            self.email.send_code(email, challenge.code)
        except Exception:
            self._store().invalidate_email_challenge(challenge.challenge_id)
            raise ApplicationError("email_delivery_unavailable") from None
        return EmailChallengeView(
            challenge_id=UUID(challenge.challenge_id),
            expires_at=challenge.expires_at,
            resend_after_seconds=challenge.resend_after_seconds,
        )

    def verify_email(
        self, *, challenge_id: UUID, code: str, client_ip: str
    ) -> CreatedIdentitySession:
        if not self.options().email:
            raise ApplicationError("email_login_unavailable")
        email = self._store().consume_email_challenge(str(challenge_id), code, client_ip)
        return self._verified_login(email=email, github_user_id=None)

    def start_github(self, *, return_to: str, client_ip: str) -> tuple[str, str]:
        if not self.options().github or self.github is None:
            raise ApplicationError("github_login_unavailable")
        self._store().limit_password("github_authorize", client_ip)
        flow = self._store().create_oauth_flow(safe_return_to(return_to))
        return self.github.authorization_url(flow.state, flow.challenge), flow.binding

    def cancel_github(self, *, state: str, binding: str) -> None:
        self._store().consume_oauth_flow(state, binding)

    def complete_github(
        self, *, code: str, state: str, binding: str
    ) -> tuple[CreatedIdentitySession, str]:
        if not self.options().github or self.github is None:
            raise ApplicationError("github_login_unavailable")
        flow = self._store().consume_oauth_flow(state, binding)
        verified = self.github.authenticate(code, flow.verifier)
        return self._verified_login(
            email=verified.email, github_user_id=verified.user_id
        ), safe_return_to(flow.return_to)

    def _verified_login(self, *, email: str, github_user_id: str | None) -> CreatedIdentitySession:
        now = datetime.now(UTC)
        # Identity creation and its first session commit together. A conflicting verified
        # email/GitHub insert is reread once after PostgreSQL resolves the unique constraint.
        for attempt in range(2):
            try:
                with self.session.begin():
                    user = (
                        self.session.scalar(
                            select(IdentityUser)
                            .where(IdentityUser.github_user_id == github_user_id)
                            .with_for_update()
                        )
                        if github_user_id is not None
                        else None
                    )
                    if user is None:
                        user = self.session.scalar(
                            select(IdentityUser)
                            .where(IdentityUser.email == email)
                            .with_for_update()
                        )
                        if (
                            user
                            and github_user_id
                            and user.github_user_id not in {None, github_user_id}
                        ):
                            raise ApplicationError("identity_link_conflict")
                        if user is None:
                            identifier = uuid4()
                            user = IdentityUser(
                                id=identifier,
                                username=f"user_{identifier.hex}",
                                email=email,
                                github_user_id=github_user_id,
                                password_hash=None,
                                credential_version=1,
                                created_at=now,
                                updated_at=now,
                            )
                            self.session.add(user)
                        elif github_user_id and user.github_user_id is None:
                            user.github_user_id, user.updated_at = github_user_id, now
                    self.session.flush()
                    return self._new_session(user, now)
            except IntegrityError:
                if attempt:
                    raise ApplicationError("identity_link_conflict") from None
        raise ApplicationError("identity_link_conflict")

    def update_credentials(
        self,
        *,
        identity: AuthenticatedIdentity,
        command: IdentityCredentialsUpdateInput,
        client_ip: str,
    ) -> None:
        verified_email = None
        self._store().limit_password(f"credentials:{identity.view.user.id}", client_ip)
        if command.challenge_id is not None and command.code is not None:
            verified_email = self._store().consume_email_challenge(
                str(command.challenge_id),
                command.code,
                client_ip,
                purpose="credentials_update",
                user_id=str(identity.view.user.id),
            )
        now = datetime.now(UTC)
        try:
            with self.session.begin():
                user = self.session.get(IdentityUser, identity.view.user.id, with_for_update=True)
                active = self.session.get(IdentitySession, identity.session_id)
                if (
                    user is None
                    or active is None
                    or active.revoked_at is not None
                    or active.expires_at <= now
                    or active.credential_version != user.credential_version
                ):
                    raise ApplicationError("invalid_session")
                if user.password_hash:
                    current = (
                        command.current_password.get_secret_value()
                        if command.current_password
                        else ""
                    )
                    valid = _PASSWORD_HASH.verify(current, user.password_hash)
                    if not valid and (verified_email is None or verified_email != user.email):
                        raise ApplicationError("credentials_verification_required")
                elif now - identity.created_at > timedelta(minutes=5) and (
                    verified_email is None or verified_email != user.email
                ):
                    raise ApplicationError("credentials_verification_required")
                user.username = command.username
                user.password_hash = _PASSWORD_HASH.hash(command.password.get_secret_value())
                user.credential_version += 1
                user.updated_at = now
                self._revoke_all(user.id, now)
        except IntegrityError:
            raise ApplicationError("username_unavailable") from None

    def _revoke_all(self, user_id: UUID, now: datetime) -> None:
        self.session.execute(
            update(IdentitySession)
            .where(IdentitySession.user_id == user_id, IdentitySession.revoked_at.is_(None))
            .values(revoked_at=now, revoked_reason="password_changed")
        )

    def create_account(
        self, *, username: str, password: str, user_id: UUID | None = None, email: str | None = None
    ) -> UUID:
        now, identifier = datetime.now(UTC), user_id or uuid4()
        if not 12 <= len(password) <= 128:
            raise ApplicationError("invalid_credentials")
        try:
            with self.session.begin():
                self.session.add(
                    IdentityUser(
                        id=identifier,
                        username=username.lower(),
                        email=email,
                        github_user_id=None,
                        password_hash=_PASSWORD_HASH.hash(password),
                        credential_version=1,
                        created_at=now,
                        updated_at=now,
                    )
                )
                self.session.flush()
        except IntegrityError:
            raise ApplicationError("username_unavailable") from None
        return identifier

    def reset_password(self, *, user_id: UUID, password: str) -> None:
        if not 12 <= len(password) <= 128:
            raise ApplicationError("invalid_credentials")
        with self.session.begin():
            user = self.session.get(IdentityUser, user_id, with_for_update=True)
            if user is None:
                raise ApplicationError("resource_not_found")
            user.password_hash = _PASSWORD_HASH.hash(password)
            user.credential_version += 1
            user.updated_at = datetime.now(UTC)
            self._revoke_all(user.id, user.updated_at)
