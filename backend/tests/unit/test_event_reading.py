from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from content.event_reading import load_event_member_content_in_transaction
from content.schemas import EventContentReadReference
from core.errors import ApplicationError
from events.reads import EventReadService


def test_bulk_event_content_read_requires_caller_transaction() -> None:
    session = cast(Session, SimpleNamespace(in_transaction=lambda: False))
    with pytest.raises(RuntimeError, match="caller's transaction"):
        load_event_member_content_in_transaction(
            session, owner_id=uuid4(), references=(), now=datetime.now(UTC)
        )


def test_bulk_event_content_read_empty_does_not_query() -> None:
    session = cast(
        Session,
        SimpleNamespace(
            in_transaction=lambda: True,
            execute=lambda *_: pytest.fail("empty read queried database"),
        ),
    )
    assert (
        load_event_member_content_in_transaction(
            session, owner_id=uuid4(), references=(), now=datetime.now(UTC)
        )
        == {}
    )


def test_read_reference_preserves_exact_content_and_version_identity() -> None:
    content_id, version_id = uuid4(), uuid4()
    reference = EventContentReadReference(content_id=content_id, content_version_id=version_id)
    assert reference.content_id == content_id
    assert reference.content_version_id == version_id
    assert reference.representative_comment_id is None


@pytest.mark.parametrize(
    ("starts_at", "ends_at"),
    [
        (datetime.now(UTC), None),
        (None, datetime.now(UTC)),
        (datetime(2026, 10, 1), datetime(2026, 10, 2)),
        (datetime.now(UTC), datetime.now(UTC) - timedelta(days=1)),
    ],
)
def test_event_time_filters_fail_before_storage(
    starts_at: datetime | None, ends_at: datetime | None
) -> None:
    service = EventReadService(cast(Session, object()))
    with pytest.raises(ApplicationError, match="invalid_event_filter"):
        service.list_events(
            owner_id=uuid4(), starts_at=starts_at, ends_at=ends_at, cursor=None, limit=20
        )


def test_invalid_event_cursor_fails_before_storage() -> None:
    service = EventReadService(cast(Session, object()))
    with pytest.raises(ApplicationError, match="invalid_event_cursor"):
        service.list_events(owner_id=uuid4(), cursor="not-json", limit=20)
