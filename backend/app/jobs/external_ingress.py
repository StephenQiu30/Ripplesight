"""Bound external source admission using the original owner-partitioned Job facts."""

from datetime import datetime, timedelta
from hashlib import sha256
from math import ceil
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from core.errors import ApplicationError
from jobs.models import Job
from jobs.schemas import JobView
from jobs.services import JobService

EXTERNAL_INGRESS_KIND = "source.editorial.ingest"


def require_external_ingress_rate_in_transaction(
    session: Session, *, owner_id: UUID, peer_hash: str, now: datetime
) -> None:
    if (
        not session.in_transaction()
        or now.utcoffset() is None
        or len(peer_hash) != 64
        or any(character not in "0123456789abcdef" for character in peer_hash)
    ):
        raise ValueError("external admission requires a private peer hash and caller transaction")
    digest = sha256(f"external-ingress:{owner_id}:{peer_hash}".encode()).digest()
    key = int.from_bytes(digest[:8], "big", signed=True)
    session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
    count, oldest = session.execute(
        select(func.count(Job.id), func.min(Job.created_at)).where(
            Job.owner_id == owner_id,
            Job.kind == EXTERNAL_INGRESS_KIND,
            Job.scope["ingress_peer_hash"].as_string() == peer_hash,
            Job.created_at > now - timedelta(seconds=60),
            Job.created_at <= now,
        )
    ).one()
    if count >= 10:
        retry = ceil((oldest + timedelta(seconds=60) - now).total_seconds()) if oldest else 60
        raise ApplicationError(
            "external_source_rate_limited", context={"retry_after_seconds": max(1, min(60, retry))}
        )


def load_external_ingress_job_in_transaction(
    session: Session, *, owner_id: UUID, job_id: UUID
) -> JobView | None:
    if not session.in_transaction():
        raise RuntimeError("external receipt requires the caller's transaction")
    row = session.scalar(
        select(Job).where(
            Job.owner_id == owner_id, Job.id == job_id, Job.kind == EXTERNAL_INGRESS_KIND
        )
    )
    return JobService._view(row) if row else None
