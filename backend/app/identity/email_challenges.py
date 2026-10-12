"""Transactional email proofs, bound to their initiating browser or session."""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from core.errors import ApplicationError
from identity.adapters.verification_store import EmailChallenge, VerificationStore
from identity.models import IdentityEmailChallenge


@dataclass(frozen=True)
class EmailProof:
    """Untrusted submission and trusted caller context, never reusable authority."""

    challenge_id: UUID
    code: str = field(repr=False)
    purpose: str
    binding_digest: bytes = field(repr=False)


class EmailChallenges:
    """Keep proof state and identity writes on the caller's PostgreSQL session."""

    def __init__(self, session: Session, store: VerificationStore) -> None:
        self.session, self.store = session, store

    def browser_binding(self, nonce: str | None) -> bytes:
        """Reject absent or malformed browser bindings rather than weakening proofs."""
        if (
            nonce is None
            or len(nonce) != 43
            or any(
                char not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
                for char in nonce
            )
        ):
            raise ApplicationError("invalid_email_code")
        return self.store.email_digest("browser", nonce)

    def session_binding(self, owner: UUID, session_id: UUID, version: int) -> bytes:
        """Bind sensitive email proof to one session and its credential generation."""
        return self.store.email_digest("session", str(owner), str(session_id), str(version))

    def prune(self) -> None:
        """Commit bounded expiry cleanup before locking a flow to avoid lock cycles."""
        expired = (
            select(IdentityEmailChallenge.scope_digest)
            .where(IdentityEmailChallenge.expires_at <= datetime.now(UTC))
            .order_by(IdentityEmailChallenge.expires_at)
            .limit(100)
            .with_for_update(skip_locked=True)
        )
        with self.session.begin():
            self.session.execute(
                delete(IdentityEmailChallenge).where(
                    IdentityEmailChallenge.scope_digest.in_(expired)
                )
            )

    def issue(self, email: str, client_ip: str, purpose: str, binding: bytes) -> EmailChallenge:
        """Replace a flow atomically; the caller sends SMTP after this commit."""
        normalized = email.strip().lower()
        scope = self.store.email_digest("scope", normalized, purpose, binding.hex())
        self.store.limit_email_send(normalized, client_ip)
        identifier, code = uuid4(), f"{secrets.randbelow(1_000_000):06d}"
        now = datetime.now(UTC)
        values = dict(
            scope_digest=scope,
            challenge_id=identifier,
            email=normalized,
            purpose=purpose,
            binding_digest=binding,
            code_digest=self.store.email_digest(
                "code", str(identifier), normalized, purpose, binding.hex(), code
            ),
            attempt_count=0,
            created_at=now,
            expires_at=now + timedelta(seconds=300),
            consumed_at=None,
            invalidated_at=None,
        )
        self.prune()
        with self.session.begin():
            statement = insert(IdentityEmailChallenge).values(**values)
            self.session.execute(
                statement.on_conflict_do_update(
                    index_elements=[IdentityEmailChallenge.scope_digest],
                    set_={key: value for key, value in values.items() if key != "scope_digest"},
                )
            )
        return EmailChallenge(str(identifier), code, now + timedelta(seconds=300))

    def invalidate(self, challenge_id: UUID) -> None:
        """Invalidate only this delivery, preserving any newer resend in its flow."""
        with self.session.begin():
            self.session.execute(
                update(IdentityEmailChallenge)
                .where(
                    IdentityEmailChallenge.challenge_id == challenge_id,
                    IdentityEmailChallenge.consumed_at.is_(None),
                )
                .values(invalidated_at=datetime.now(UTC))
            )

    def consume_in_transaction(self, proof: EmailProof) -> IdentityEmailChallenge | None:
        """Lock and stage consumption; caller commits failed attempts before rejection.

        Correct proofs are consumed only with the surrounding identity transaction.
        No caller may acquire this lock after acquiring user or session locks.
        """
        row = self.session.scalar(
            select(IdentityEmailChallenge)
            .where(
                IdentityEmailChallenge.challenge_id == proof.challenge_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        now = datetime.now(UTC)
        if (
            row is None
            or row.consumed_at is not None
            or row.invalidated_at is not None
            or row.expires_at <= now
            or row.attempt_count >= 5
        ):
            return None
        digest = self.store.email_digest(
            "code",
            str(row.challenge_id),
            row.email,
            row.purpose,
            row.binding_digest.hex(),
            proof.code,
        )
        scope = self.store.email_digest("scope", row.email, row.purpose, row.binding_digest.hex())
        if (
            row.purpose != proof.purpose
            or not secrets.compare_digest(row.binding_digest, proof.binding_digest)
            or not secrets.compare_digest(row.code_digest, digest)
            or not secrets.compare_digest(row.scope_digest, scope)
        ):
            row.attempt_count += 1
            return None
        row.consumed_at = now
        return row
