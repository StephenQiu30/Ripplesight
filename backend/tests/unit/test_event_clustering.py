from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from core.config import Settings
from events.clustering import build_event_prompt, candidate_fingerprint
from events.schemas import EventDecision, EventInput
from events.services import EventClusterExecutor
from jobs.execution import JobExecutionFailure


def _member(title: str) -> EventInput:
    return EventInput(
        owner_id=uuid4(),
        topic_id=uuid4(),
        content_id=uuid4(),
        content_version_id=uuid4(),
        source_key="hackernews",
        title=title,
        body=None,
        first_seen_at=datetime(2026, 9, 28, tzinfo=UTC),
        first_seen_basis="discovered",
        matched_keywords=frozenset({"Acme"}),
    )


def test_candidate_fingerprint_and_prompt_are_order_independent() -> None:
    topic_id = uuid4()
    first, second = _member("Acme launches a model"), _member("Acme launches new model")
    assert candidate_fingerprint(
        topic_id=topic_id, members=(first, second)
    ) == candidate_fingerprint(topic_id=topic_id, members=(second, first))
    assert build_event_prompt((first, second)) == build_event_prompt((second, first))


def test_model_confirmation_rejects_blank_title_and_duplicate_members() -> None:
    first, second = uuid4(), uuid4()
    with pytest.raises(ValidationError):
        EventDecision(
            same_event=True,
            member_version_ids=[first, second],
            title=" ",
            summary="摘要",
        )
    with pytest.raises(ValidationError):
        EventDecision(
            same_event=True,
            member_version_ids=[first, first],
            title="事件",
            summary="摘要",
        )


def test_event_executor_does_not_open_storage_or_model_when_disabled() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://test:test@127.0.0.1:5432/hotkey_test",
        ai_enabled=True,
        events_cluster_enabled=False,
    )
    executor = EventClusterExecutor(
        SimpleNamespace(__call__=lambda: pytest.fail("opened event storage")), settings
    )
    with pytest.raises(JobExecutionFailure, match="event_clustering_disabled"):
        executor.execute(SimpleNamespace(kind="events.cluster"))
