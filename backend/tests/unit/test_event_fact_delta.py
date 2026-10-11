"""Verify permission and association projection without fabricating historical changes."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from events.fact_delta import load_revision_delta_in_transaction
from events.fact_schemas import (
    EventFactMemberView,
    EventFactView,
    EventMaterialChange,
    EventRevisionDeltaReceipt,
)
from events.schemas import EventEvidenceChangeDecision, EventFactDecision


@pytest.mark.parametrize("gate", ["partial", "removed", "mention", "unlinked", "readable"])
def test_current_gate_hides_frozen_judgment_and_retains_denominator(gate):
    owner, topic, event, fact, member, version, call = (uuid4() for _ in range(7))
    judgment = EventEvidenceChangeDecision(
        member_version_id=version, kind="supplement", reason="extra evidence"
    )
    group = EventFactDecision(
        member_version_ids=[version],
        title="old fact",
        summary="existing occurrence",
        relation="same_occurrence",
        existing_fact_id=fact,
        evidence_changes=[judgment],
    )
    receipt = EventRevisionDeltaReceipt(
        version="fact_delta_v1",
        event_id=event,
        baseline_event_revision=1,
        event_revision=2,
        material_changes=[
            EventMaterialChange(
                event_member_id=member,
                content_version_id=version,
                fact_id=fact,
                kind="supplement",
                reason=judgment.reason,
            )
        ],
    )
    assessment = SimpleNamespace(
        status="valid",
        input_fingerprint=b"same",
        ai_call_id=call,
        decisions=[group.model_dump(mode="json")],
        input_snapshot={
            "facts": [{"fact_id": str(fact), "event_id": str(event), "relation": "root"}]
        },
        applied_result=receipt.model_dump(mode="json"),
    )
    candidate = SimpleNamespace(
        input_fingerprint=b"same",
        ai_call_id=call,
        member_version_ids=[str(version)],
        expected_event_revisions={str(event): 1},
    )
    assignment = SimpleNamespace(fact_id=fact, added_revision=1, relation="root")
    viewed = EventFactView(
        id=fact,
        revision=2,
        relation="root",
        root_fact_id=None,
        title=None if gate == "partial" else "existing fact",
        summary=None,
        first_seen_at=datetime.now(UTC),
        first_seen_basis="discovered",
        evidence_state="partial" if gate == "partial" else "complete",
        members=[
            EventFactMemberView(
                content_id=uuid4(),
                content_version_id=version,
                event_member_id=member,
                role="mention" if gate == "mention" else "report",
                assignment_origin="model",
                availability="readable",
            )
        ],
    )
    stored = SimpleNamespace(
        id=member,
        content_version_id=version,
        added_revision=2,
        removed_revision=3 if gate == "removed" else None,
    )
    session = MagicMock()
    session.execute.side_effect = [
        SimpleNamespace(all=lambda: [(assessment, candidate)]),
        SimpleNamespace(all=lambda: [] if gate == "unlinked" else [(member, fact)]),
    ]
    state, delta = load_revision_delta_in_transaction(
        session,
        event=SimpleNamespace(owner_id=owner, topic_id=topic, id=event),
        revision=2,
        facts=[viewed],
        members=[stored],
        assignments=[assignment],
    )
    assert state == "available" and delta is not None and delta.material_count == 1
    assert delta.supplement_count == (1 if gate == "readable" else 0)
    assert delta.unknown_count == (0 if gate == "readable" else 1)
    assert delta.material_changes[0].reason == (judgment.reason if gate == "readable" else None)
    assert delta.material_changes[0].unavailable is (gate != "readable")


@pytest.mark.parametrize(
    "rows, expected",
    [([], "not_recorded"), ([(object(), object()), (object(), object())], "ambiguous")],
)
def test_missing_or_ambiguous_receipt_is_unknown_without_historical_reconstruction(rows, expected):
    session = MagicMock()
    session.execute.return_value.all.return_value = rows
    state, delta = load_revision_delta_in_transaction(
        session,
        event=SimpleNamespace(owner_id=uuid4(), topic_id=uuid4(), id=uuid4()),
        revision=1,
        facts=[],
        members=[],
        assignments=[],
    )
    assert state == expected and delta is None
    session.execute.assert_called_once()
