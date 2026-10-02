from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from analysis.translation_schemas import TranslationReadView
from analysis.translation_services import ContentTranslationService


def translated_body_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    content_id: UUID,
    content_version_id: UUID,
    policy_revision: int,
    now: datetime,
) -> TranslationReadView:
    if not session.in_transaction():
        raise RuntimeError("translation reading requires caller transaction")
    service = ContentTranslationService(session, clock=lambda: now)
    row = service._latest(owner_id, content_id, content_version_id, policy_revision)
    if row is None:
        return TranslationReadView()
    view = service._view(row)
    return TranslationReadView.model_validate(view)
