from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from jobs.models import Job


@dataclass(frozen=True)
class CollectionSourceScope:
    job_id: UUID
    source_key: str
    selector_ref: str


def collection_selector_reference(
    kind: str, source_key: str, scope: Mapping[str, object]
) -> str | None:
    """Identify an accepted request, independently of stable content identity."""
    if kind in {"keyword.search", "source.comments"}:
        target = scope.get("target_hash")
        if not isinstance(target, str) or not re.fullmatch(r"[0-9a-f]{64}", target):
            return None
        prefix = "search" if kind == "keyword.search" else "comments"
        return f"{prefix}:{target}"
    if kind == "source.hotlist" and re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", source_key):
        return f"hotlist:{source_key}"
    if kind == "webpage.collect" and source_key == "web":
        target = scope.get("target_url")
        if not isinstance(target, str):
            return None
        try:
            parsed = urlsplit(target)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username:
                return None
        except ValueError:
            return None
        return f"page:{hashlib.sha256(target.encode()).hexdigest()}"
    return None


def load_collection_source_scopes_in_transaction(
    session: Session, *, owner_id: UUID, job_ids: tuple[UUID, ...]
) -> dict[UUID, CollectionSourceScope]:
    if not session.in_transaction():
        raise RuntimeError("collection scope reads require the caller's transaction")
    if len(job_ids) > 1000:
        raise ValueError("at most 1000 job scopes may be loaded")
    result: dict[UUID, CollectionSourceScope] = {}
    if not job_ids:
        return result
    rows = session.execute(
        select(Job.id, Job.source_key, Job.kind, Job.scope).where(
            Job.owner_id == owner_id, Job.id.in_(job_ids)
        )
    )
    for job_id, source_key, kind, scope in rows:
        reference = collection_selector_reference(kind, source_key or "", scope)
        if reference is not None and source_key is not None:
            result[job_id] = CollectionSourceScope(job_id, source_key, reference)
    return result
