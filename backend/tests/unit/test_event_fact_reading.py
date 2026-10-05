from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from events.fact_models import EventFact
from events.facts import EventFactReadService
from events.models import Event, EventMember
from events.observation_inputs import event_content_reference

NOW = datetime(2026, 10, 5, tzinfo=UTC)


@pytest.mark.parametrize(
    ("all_members_readable", "status", "frame", "evidence", "conditions"),
    [
        (
            True,
            "confirmed",
            {"evidence": "Original evidence.", "conditions": [{"quote": "Pro users only."}]},
            "Original evidence.",
            ["Pro users only."],
        ),
        (
            False,
            "confirmed",
            {"evidence": "Original evidence.", "conditions": [{"quote": "Pro users only."}]},
            None,
            [],
        ),
        (
            True,
            "unreviewed",
            {"evidence": "Original evidence.", "conditions": [{"quote": "Pro users only."}]},
            None,
            [],
        ),
        (True, "confirmed", {"subject": "Legacy publisher"}, None, []),
        (True, "confirmed", None, None, []),
    ],
)
def test_fact_quotes_require_confirmed_status_and_all_fixed_members(
    monkeypatch: pytest.MonkeyPatch,
    all_members_readable: bool,
    status: str,
    frame: dict[str, object] | None,
    evidence: str | None,
    conditions: list[str],
) -> None:
    owner, event_id, fact_id = UUID(int=1), UUID(int=2), UUID(int=3)
    member = EventMember(
        id=UUID(int=4),
        owner_id=owner,
        event_id=event_id,
        content_id=UUID(int=5),
        content_version_id=UUID(int=6),
        source_key="x",
        observation_id=None,
        input_manifest=None,
        observation_source_key=None,
        representative_comment_id=None,
        representative_comment_observation_id=None,
    )
    fact_member = SimpleNamespace(
        fact_id=fact_id,
        content_id=member.content_id,
        content_version_id=member.content_version_id,
        event_member_id=member.id,
        role="primary",
        assignment_origin="model",
    )
    reference = event_content_reference(member)
    # The displayed event's member is readable in every case. An unavailable
    # member in another assignment or quoted post must still hide the fact text.
    monkeypatch.setattr(
        "events.facts.load_event_member_content_in_transaction",
        lambda *args, **kwargs: {
            reference: SimpleNamespace(representative_comment_state="available")
        },
    )
    gate = MagicMock(return_value={fact_id: (UUID(int=7),)} if all_members_readable else {})
    monkeypatch.setattr("events.facts.load_fact_observation_inputs_in_transaction", gate)
    session = MagicMock()
    session.scalar.return_value = Event(id=event_id, owner_id=owner, revision=1, status="active")
    session.scalars.return_value = [
        SimpleNamespace(fact_id=fact_id, root_fact_id=None, relation="root")
    ]
    session.execute.return_value.__iter__.return_value = [(fact_member, member)]
    session.get.return_value = EventFact(
        id=fact_id,
        revision=1,
        status=status,
        frame=frame,
        title="Fact title",
        summary="Fact summary",
        first_seen_at=NOW,
        first_seen_basis="published",
    )
    view = EventFactReadService(session).list_facts(owner_id=owner, event_id=event_id)
    fact = view.facts[0]
    assert fact.evidence == evidence and [item.quote for item in fact.conditions] == conditions
    assert fact.evidence_state == ("complete" if all_members_readable else "partial")
    if not all_members_readable or status != "confirmed":
        assert fact.title is None and fact.summary is None
    assert gate.call_args.kwargs["fact_ids"] == (fact_id,)
    assert gate.call_args.kwargs["owner_id"] == owner
