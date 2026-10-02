"""Bounded rechecks of accepted URLs from the existing operator audit receipts."""

from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from operations.indexnow_schemas import IndexNowReceiptCursor
from publication.indexnow_reading import read_indexable_path_eligibilities_in_transaction


def load_changed_receipt_paths_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    after: IndexNowReceiptCursor | None,
    until: datetime,
    limit: int = 500,
) -> tuple[list[str], IndexNowReceiptCursor | None, int]:
    if not session.in_transaction() or until.utcoffset() is None or not 1 <= limit <= 500:
        raise ValueError("receipt recheck requires a bounded aware caller transaction")
    cursor_filter = ""
    parameters: dict[str, object] = {"owner": owner_id, "until": until, "limit": limit}
    if after is not None:
        cursor_filter = "AND (audit.created_at,audit.id,entry.key) > (:at,:id,:path)"
        parameters.update(at=after.created_at, id=after.audit_id, path=after.path)
    rows = session.execute(
        text(
            "SELECT audit.created_at,audit.id,entry.key FROM operations_audit_operations audit "
            "CROSS JOIN LATERAL jsonb_each(CASE WHEN "
            "jsonb_typeof(audit.after_state->'eligibilities')='object' "
            "THEN audit.after_state->'eligibilities' ELSE '{}'::jsonb END) entry "
            "WHERE audit.owner_id=:owner AND audit.action='indexnow.submit' "
            "AND audit.status='succeeded' AND audit.created_at<=:until "
            "AND audit.after_state->>'stage' IN ('accepted','key_validation_pending') "
            + cursor_filter
            + " ORDER BY audit.created_at,audit.id,entry.key LIMIT :limit"
        ),
        parameters,
    ).all()
    if not rows:
        return [], after, 0
    paths = sorted({cast(str, row.key) for row in rows})
    # Compare with the latest successful submission, so old true receipts cannot
    # continually resend a removal already accepted as false by a later receipt.
    latest = session.execute(
        text(
            "SELECT DISTINCT ON (entry.key) entry.key,entry.value "
            "FROM operations_audit_operations audit "
            "CROSS JOIN LATERAL jsonb_each(CASE WHEN "
            "jsonb_typeof(audit.after_state->'eligibilities')='object' "
            "THEN audit.after_state->'eligibilities' ELSE '{}'::jsonb END) entry "
            "WHERE audit.owner_id=:owner AND audit.action='indexnow.submit' "
            "AND audit.status='succeeded' AND audit.created_at<=:until "
            "AND audit.after_state->>'stage' IN ('accepted','key_validation_pending') "
            "AND entry.key=ANY(:paths) "
            "ORDER BY entry.key,audit.created_at DESC,audit.id DESC"
        ),
        {"owner": owner_id, "until": until, "paths": paths},
    ).all()
    current = read_indexable_path_eligibilities_in_transaction(
        session, owner_id=owner_id, paths=paths, now=until
    )
    changed = sorted(row.key for row in latest if current[row.key] != row.value)
    last = rows[-1]
    return (
        changed,
        IndexNowReceiptCursor(created_at=last.created_at, audit_id=last.id, path=last.key),
        len(rows),
    )
