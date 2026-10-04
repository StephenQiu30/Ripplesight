"""Expose the original successful analysis Job reference without leaking AI ORM."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai.models import AiCall


def load_legacy_analysis_call_job_in_transaction(
    session: Session, *, owner_id: UUID, ai_call_id: UUID, prompt_version: str
) -> UUID | None:
    if not session.in_transaction():
        raise RuntimeError("legacy analysis call reads require the caller's transaction")
    return session.scalar(
        select(AiCall.job_id).where(
            AiCall.owner_id == owner_id,
            AiCall.id == ai_call_id,
            AiCall.purpose == "analysis.annotate",
            AiCall.prompt_version == prompt_version,
            AiCall.status == "succeeded",
            AiCall.job_id.is_not(None),
        )
    )
