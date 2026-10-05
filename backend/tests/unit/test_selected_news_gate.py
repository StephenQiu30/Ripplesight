"""AIHOT selected-news-gate semantics with existing, controlled relation evidence."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from analysis.editorial_reading import record_editorial_selection_in_transaction
from analysis.editorial_schemas import (
    EditorialPublicationInputView,
    EditorialResultView,
    EditorialRunView,
    EditorialSourceView,
    EditorialWritingView,
    StructureOutput,
)
from analysis.editorial_selection import (
    EditorialSelectionCandidate,
    EditorialSelectionGate,
    decide_editorial_selection,
)
from core.config import Settings
from events.fact_schemas import EventPublicationGrouping
from publication.projection import derive_projection
from publication.schemas import SourcePolicyView
from tests.unit.test_editorial_rules import material

NOW = datetime(2026, 10, 5, tzinfo=UTC)
EVENT, ROOT = UUID(int=100), UUID(int=101)


def candidate(
    number=1,
    *,
    fact_id=ROOT,
    relation="root",
    quote="Acme released model A.",
    subject="Acme",
    action="release",
    object="model A",
    conditions=(),
    first_party=False,
    score=90,
    manual=False,
    grouped=True,
    scope="single",
    evidence=True,
    eligible=True,
    at=NOW,
    body_complete=True,
    occurred_at=None,
    grouping_enabled=True,
    grouping_in_scope=True,
):
    original = material(
        content_id=UUID(int=number),
        content_version_id=UUID(int=number + 1000),
        body=quote + " " + " ".join(conditions),
        body_complete=body_complete,
        published_at=at,
        discovered_at=at,
    )
    source = EditorialSourceView(
        source_key=original.source_key,
        revision=1,
        tier="T1",
        source_kind="rss",
        name="受控来源",
        first_party=first_party,
        owner_entity_id=None,
        tags=[],
        enabled=True,
    )
    structure = StructureOutput(
        category="ai-models",
        tags=[],
        subjects=[],
        scope=scope,
        fact={
            "title": "模型发布",
            "subject": subject,
            "action": action,
            "object": object,
            "evidence": quote if evidence else None,
            "conditions": [{"quote": q} for q in conditions],
            "occurredAt": occurred_at,
        },
    )
    run = EditorialRunView(
        id=uuid4(),
        job_id=uuid4(),
        content_id=original.content_id,
        content_version_id=original.content_version_id,
        source_key=source.source_key,
        source_revision=1,
        prompt_version="test",
        manual_version=int(manual),
        status="complete",
        failure_code=None,
        created_at=at,
        updated_at=at,
        result=EditorialResultView(
            relevance="pass",
            selected=True,
            score=score,
            structure=structure,
            manual=manual,
            manual_overrides={"selected": True} if manual else {},
            writing=EditorialWritingView(
                title_zh=f"新闻写法{number}",
                summary_zh="同一新闻的不同中文说法",
                kind="understand",
                identity_guard={
                    "outcome": "pass",
                    "unsupported_title_entity_ids": [],
                    "unsupported_summary_entity_ids": [],
                },
            ),
        ),
    )
    snapshot = EditorialPublicationInputView(
        run=run,
        source=source,
        material=original,
        timeline_at=at,
        first_received_at=at,
        backfill=None,
    )
    grouping = (
        EventPublicationGrouping(
            topic_id=UUID(int=90),
            event_id=EVENT,
            event_revision=1,
            fact_id=fact_id,
            root_fact_id=None if relation == "root" else ROOT,
            fact_revision=1,
            grouped_at=at,
            role="primary",
            relation=relation,
            assignment_origin="model",
        )
        if grouped
        else None
    )
    return EditorialSelectionCandidate(
        snapshot, grouping, eligible, grouping_enabled, grouping_in_scope
    )


def policy():
    return SourcePolicyView(
        source_key="rss_test",
        revision=1,
        participation_mode="editorial",
        site_fulltext=False,
        syndicate_fulltext=False,
        indexable=False,
        release_delay_seconds=180,
        license_name="fixture",
        license_url=None,
        updated_at=NOW,
    )


def test_rewording_the_same_news_has_zero_extra_selected_reports():
    first, rewritten = candidate(), candidate(2, quote="Model A has been unveiled by Acme.")
    gates = decide_editorial_selection([rewritten, first])
    assert sum(gate.selected for gate in gates.values()) == 1
    assert gates[UUID(int=2)].state == "duplicate"
    assert gates[UUID(int=2)].representative_id == UUID(int=1)
    assert gates == decide_editorial_selection([first, rewritten])


def test_first_party_wins_over_fulltext_score_and_time():
    media = candidate(score=100)
    official = candidate(
        2, first_party=True, body_complete=False, score=80, at=NOW + timedelta(minutes=1)
    )
    gates = decide_editorial_selection([media, official])
    assert gates[UUID(int=2)].selected and not gates[UUID(int=1)].selected


def test_no_new_information_followup_stays_in_all():
    followup = candidate(
        2,
        fact_id=UUID(int=102),
        relation="development",
        quote="A reminder: Acme has released model A.",
        at=NOW + timedelta(seconds=1),
    )
    gate = decide_editorial_selection([candidate(), followup])[UUID(int=2)]
    assert gate.state == "redundant" and gate.reason == "no_new_information"
    projection = derive_projection(
        followup.snapshot,
        policy(),
        now=NOW + timedelta(hours=1),
        grouping=followup.grouping,
        selection=gate,
    )
    assert projection.eligible and not projection.selected


@pytest.mark.parametrize(
    "delta",
    [
        {"quote": "Acme released model A with 30% faster inference."},
        {"quote": "Acme released model A.", "conditions": ("Only paid accounts can use it.",)},
        {"quote": "Acme fixed model A.", "action": "fix"},
        {"quote": "Acme released model B.", "object": "model B"},
        {"quote": "Beta acquired model A.", "subject": "Beta", "action": "acquire"},
    ],
)
def test_grounded_new_facts_numbers_conditions_and_actor_actions_are_not_blocked(delta):
    update = candidate(
        2, fact_id=UUID(int=102), relation="development", at=NOW + timedelta(seconds=1), **delta
    )
    gates = decide_editorial_selection([candidate(), update])
    assert gates[UUID(int=1)].selected and gates[UUID(int=2)].selected


@pytest.mark.parametrize("missing", ["grouping", "evidence", "scope", "object"])
def test_unresolved_never_becomes_selected_after_a_deadline_and_exposes_review(missing):
    item = candidate(
        grouped=missing != "grouping",
        evidence=missing != "evidence",
        scope="unknown" if missing == "scope" else "single",
        object=None if missing == "object" else "model A",
    )
    gate = decide_editorial_selection([item])[UUID(int=1)]
    assert gate.state == "requires_review"
    for at in (NOW, NOW + timedelta(days=1)):
        projected = derive_projection(
            item.snapshot, policy(), now=at, grouping=item.grouping, selection=gate
        )
        assert projected.eligible and not projected.selected and projected.visible_after is None
    row = SimpleNamespace(result=item.snapshot.run.result.model_dump(), failure_code=None)
    session = SimpleNamespace(in_transaction=lambda: True, scalar=lambda _: row)
    record_editorial_selection_in_transaction(
        session, owner_id=uuid4(), snapshot=item.snapshot, gate=gate
    )
    assert row.failure_code == "editorial_selection_requires_review"
    assert row.result["selection_gate"]["state"] == "requires_review"
    assert row.result["selected"] is True  # original scoring evidence is retained
    record_editorial_selection_in_transaction(
        session,
        owner_id=uuid4(),
        snapshot=item.snapshot,
        gate=EditorialSelectionGate("selected", "manual_confirmed", UUID(int=1)),
    )
    assert row.failure_code is None


def test_manual_value_and_grouping_are_preserved_but_one_occurrence_still_has_one_seat():
    original = candidate()
    update = candidate(
        2, fact_id=UUID(int=102), relation="development", manual=True, at=NOW + timedelta(seconds=1)
    )
    before = update.snapshot.run.result.model_dump()
    gates = decide_editorial_selection([original, update])
    assert gates[UUID(int=2)].selected
    assert update.snapshot.run.result.model_dump() == before
    # The existing events correction marks assignment_origin, without editing scoring evidence.
    grouped = replace(
        update,
        snapshot=original.snapshot,
        grouping=replace(update.grouping, assignment_origin="manual"),
    )
    assert decide_editorial_selection([grouped])[UUID(int=1)].selected
    duplicate = candidate(3, manual=True)
    assert sum(g.selected for g in decide_editorial_selection([original, duplicate]).values()) == 1


def test_projection_fails_closed_without_gate_even_for_manual_and_undated_cannot_bypass():
    item = candidate(manual=True)
    assert not derive_projection(item.snapshot, policy(), now=NOW).selected
    snapshot = item.snapshot.model_copy(
        update={"material": item.snapshot.material.model_copy(update={"published_at": None})}
    )
    assert not derive_projection(
        snapshot,
        policy(),
        now=NOW,
        selection=EditorialSelectionGate("selected", "manual_confirmed", UUID(int=1)),
    ).selected


def test_unselected_reports_do_not_suppress_information_missing_from_the_representative():
    root = candidate(first_party=True)
    detail = candidate(2, quote="Model A is 30% faster.")
    repeat = candidate(
        3,
        fact_id=UUID(int=102),
        relation="development",
        quote="Model A is 30% faster.",
        at=NOW + timedelta(seconds=1),
    )
    gates = decide_editorial_selection([root, detail, repeat])
    assert gates[UUID(int=1)].selected
    assert gates[UUID(int=3)].selected


@pytest.mark.parametrize("readable", [True, False])
@pytest.mark.parametrize("grouping_enabled", [True, False])
@pytest.mark.parametrize("visibility", ["public", "summary-only", "withdrawn"])
def test_gate_recalls_a_preferred_peer_outside_the_requested_page_and_rechecks_permission(
    monkeypatch,
    readable,
    grouping_enabled,
    visibility,
):
    import publication.selection as module

    requested, official = candidate(), candidate(2, first_party=True)
    rows = [
        SimpleNamespace(
            content_id=item.snapshot.material.content_id,
            content_version_id=item.snapshot.material.content_version_id,
            source_key=item.snapshot.material.source_key,
            override={"visibility": visibility} if item is official else {},
            data={"editorial_run_id": str(item.snapshot.run.id), "manual_version": 0},
        )
        for item in (requested, official)
    ]
    policy_row = SimpleNamespace(
        source_key=requested.snapshot.material.source_key,
        configuration={"participation_mode": "editorial"},
    )
    session = SimpleNamespace(
        in_transaction=lambda: True,
        scalars=lambda query: [policy_row] if "publication_source_policies" in str(query) else rows,
        info={
            "settings": Settings(
                environment="test",
                database_url="postgresql+psycopg://test:test@127.0.0.1:5432/hotkey_test_selection",
                events_cluster_enabled=grouping_enabled,
            )
        },
    )
    monkeypatch.setattr(
        module, "get_settings", lambda: pytest.fail("must use the injected process settings")
    )
    monkeypatch.setattr(
        module, "load_selection_grouping_exempt_ids_in_transaction", lambda *a, **k: frozenset()
    )
    monkeypatch.setattr(
        module,
        "load_publication_groupings_in_transaction",
        lambda *a, **k: {
            item.snapshot.material.content_id: item.grouping
            for item in (requested, official)
            if item.snapshot.material.content_id in k["content_versions"]
        },
    )
    monkeypatch.setattr(
        module,
        "load_selection_peer_ids_in_transaction",
        lambda *a, **k: tuple(row.content_id for row in rows),
    )
    monkeypatch.setattr(
        module,
        "load_editorial_publication_inputs_in_transaction",
        lambda *a, **k: {UUID(int=2): official.snapshot} if readable else {},
    )
    context = module.load_publication_selection_in_transaction(
        session, owner_id=uuid4(), snapshots={UUID(int=1): requested.snapshot}, now=NOW
    )
    preferred_eligible = readable and visibility != "withdrawn"
    assert context.gates[UUID(int=1)].selected is not preferred_eligible
    if preferred_eligible:
        assert context.gates[UUID(int=1)].representative_id == UUID(int=2)
        assert context.gates[UUID(int=2)].selected

    # A pending visibility correction must use the same gate as subsequent reads.
    corrected = module.load_publication_selection_in_transaction(
        session,
        owner_id=uuid4(),
        snapshots={UUID(int=1): requested.snapshot},
        now=NOW,
        visibility_overrides={
            UUID(int=2): "summary-only" if visibility == "withdrawn" else "withdrawn"
        },
    )
    preferred_eligible = readable and visibility == "withdrawn"
    assert corrected.gates[UUID(int=1)].selected is not preferred_eligible
    if preferred_eligible:
        assert corrected.gates[UUID(int=2)].selected


def test_an_unverifiable_previous_manual_fact_does_not_manufacture_incremental_information():
    previous = candidate(manual=True, evidence=False)
    update = candidate(
        2, relation="development", fact_id=UUID(int=102), at=NOW + timedelta(seconds=1)
    )
    gates = decide_editorial_selection([previous, update])
    assert gates[UUID(int=1)].selected
    assert gates[UUID(int=2)].state == "requires_review"


@pytest.mark.parametrize("quote", ["Acme ... released A.", "Acme\nreleased A."])
def test_historical_ungrounded_or_discarded_quotes_do_not_become_selection_evidence(quote):
    item = candidate(quote=quote)
    assert decide_editorial_selection([item])[UUID(int=1)].state == "requires_review"


def test_refreshing_selection_review_code_does_not_republish_identical_evidence():
    item = candidate()
    gate = decide_editorial_selection([item])[UUID(int=1)]
    reviewed = derive_projection(
        item.snapshot, policy(), now=NOW, grouping=item.grouping, selection=gate
    )
    pending = item.snapshot.model_copy(
        update={
            "run": item.snapshot.run.model_copy(
                update={"failure_code": "editorial_selection_requires_review"}
            )
        }
    )
    assert (
        derive_projection(
            pending, policy(), now=NOW, grouping=item.grouping, selection=gate
        ).input_fingerprint
        == reviewed.input_fingerprint
    )


@pytest.mark.parametrize("number", ["30 %", "30.0%"])
def test_numeric_formatting_is_not_new_information(number):
    root = candidate(quote="Model A improves speed by 30%.")
    followup = candidate(
        2,
        quote=f"Model A improves speed by {number}.",
        fact_id=UUID(int=102),
        relation="development",
        at=NOW + timedelta(seconds=1),
    )
    assert decide_editorial_selection([root, followup])[UUID(int=2)].state == "redundant"


def test_a_changed_numeric_unit_is_new_information():
    root = candidate(quote="Model A needs 30 GB of memory.")
    followup = candidate(
        2,
        quote="Model A needs 30 MB of memory.",
        fact_id=UUID(int=102),
        relation="development",
        at=NOW + timedelta(seconds=1),
    )
    assert decide_editorial_selection([root, followup])[UUID(int=2)].selected


def test_a_changed_numeric_sign_is_new_information():
    root = candidate(quote="Model A changes throughput by +30%.")
    followup = candidate(
        2,
        quote="Model A changes throughput by -30%.",
        fact_id=UUID(int=102),
        relation="development",
        at=NOW + timedelta(seconds=1),
    )
    assert decide_editorial_selection([root, followup])[UUID(int=2)].selected


@pytest.mark.parametrize(
    "incomplete",
    [{}, {"evidence": False}, {"scope": "unknown"}, {"object": None}, {"quote": "Acme ... A."}],
)
def test_disabled_grouping_preserves_single_automatic_selection_and_incomplete_facts(incomplete):
    item = candidate(grouped=False, grouping_enabled=False, **incomplete)
    gate = decide_editorial_selection([item])[UUID(int=1)]
    assert gate.selected and gate.reason == "grouping_disabled"
    assert gate.representative_id == UUID(int=1)
    projected = derive_projection(item.snapshot, policy(), now=NOW, selection=gate)
    assert projected.selected and projected.fact_id is None and projected.event_id is None


def test_disabled_grouping_exact_normalized_identity_has_one_first_party_representative():
    media = candidate(grouped=False, grouping_enabled=False, score=100)
    official = candidate(
        2,
        grouped=False,
        grouping_enabled=False,
        first_party=True,
        subject=" ACME ",
        action=" Release ",
        object="MODEL   A",
        score=80,
        at=NOW + timedelta(minutes=1),
    )
    gates = decide_editorial_selection([media, official])
    assert gates[UUID(int=2)].selected
    assert gates[UUID(int=1)] == EditorialSelectionGate("duplicate", "same_occurrence", UUID(int=2))
    assert gates == decide_editorial_selection([official, media])


@pytest.mark.parametrize("occurred_at", [None, "2026-10-04"])
def test_disabled_grouping_same_occurrence_does_not_expand_from_losing_reports(occurred_at):
    root = candidate(grouped=False, grouping_enabled=False, occurred_at=occurred_at)
    detail = candidate(
        2,
        grouped=False,
        grouping_enabled=False,
        occurred_at=occurred_at,
        quote="Model A is 30% faster.",
        at=NOW + timedelta(minutes=1),
    )
    update = candidate(
        3,
        grouped=False,
        grouping_enabled=False,
        quote="Model A is 30% faster.",
        at=NOW + timedelta(days=1),
    )
    gates = decide_editorial_selection([root, detail, update])
    assert gates[UUID(int=1)].selected and gates[UUID(int=2)].state == "duplicate"
    assert gates[UUID(int=3)].selected


@pytest.mark.parametrize("new_information", [False, True])
def test_disabled_grouping_followups_use_the_existing_information_gate(new_information):
    root = candidate(grouped=False, grouping_enabled=False)
    update = candidate(
        2,
        grouped=False,
        grouping_enabled=False,
        at=NOW + timedelta(days=1),
        quote="Model A is 30% faster." if new_information else "A reminder: Acme released model A.",
    )
    gates = decide_editorial_selection([update, root])
    gate = gates[UUID(int=2)]
    assert gate.selected is new_information
    assert gate.reason == ("grouping_disabled" if new_information else "no_new_information")


def test_disabled_grouping_uses_beijing_publication_day_when_occurrence_is_unknown():
    first = candidate(grouped=False, grouping_enabled=False, at=NOW - timedelta(hours=9))
    same_day = candidate(2, grouped=False, grouping_enabled=False, at=NOW - timedelta(hours=8))
    # A UTC date change alone is not a new Beijing publication day.
    another = candidate(3, grouped=False, grouping_enabled=False, at=NOW)
    gates = decide_editorial_selection([first, same_day, another])
    assert gates[UUID(int=1)].selected  # Beijing October 4
    assert gates[UUID(int=2)].state == "redundant"  # Beijing October 5, no increment
    assert gates[UUID(int=3)].state == "redundant"
    same = decide_editorial_selection([same_day, another])
    assert same[UUID(int=3)].state == "duplicate"


@pytest.mark.parametrize(
    ("first_date", "next_date", "selected"),
    [("2026-10-04", "2026-10-04", False), ("2026-10-04", "2026-10-05", True)],
)
def test_disabled_grouping_occurrence_dates_take_priority_over_publication_days(
    first_date,
    next_date,
    selected,
):
    first = candidate(grouped=False, grouping_enabled=False, occurred_at=first_date)
    followup = candidate(
        2,
        grouped=False,
        grouping_enabled=False,
        occurred_at=next_date,
        at=NOW + timedelta(days=1),
    )
    gate = decide_editorial_selection([first, followup])[UUID(int=2)]
    assert gate.selected is selected
    if not selected:
        assert gate.state == "duplicate"


def test_enabled_grouping_unresolved_remains_visible_for_review():
    item = candidate(grouped=False, grouping_enabled=True)
    gate = decide_editorial_selection([item])[UUID(int=1)]
    assert gate == EditorialSelectionGate("requires_review", "grouping_unresolved")
    projected = derive_projection(item.snapshot, policy(), now=NOW, selection=gate)
    assert projected.eligible and not projected.selected


def test_material_explicitly_outside_grouping_scope_preserves_automatic_selection():
    item = candidate(
        grouped=False, grouping_enabled=True, grouping_in_scope=False, scope="composite"
    )
    gate = decide_editorial_selection([item])[UUID(int=1)]
    assert gate.selected and gate.reason == "grouping_out_of_scope"


def test_disabled_grouping_never_merges_incomplete_facts_or_different_objects():
    items = [
        candidate(1, grouped=False, grouping_enabled=False, evidence=False),
        candidate(2, grouped=False, grouping_enabled=False, evidence=False),
        candidate(3, grouped=False, grouping_enabled=False),
        candidate(4, grouped=False, grouping_enabled=False, object="model B"),
    ]
    assert all(gate.selected for gate in decide_editorial_selection(items).values())


def test_grouping_scope_reuses_isolated_standalone_and_composite_contracts(monkeypatch):
    import events.facts as module
    from events.schemas import EventInput

    owner, topic = uuid4(), uuid4()
    inputs = tuple(
        EventInput(
            owner_id=owner,
            topic_id=topic,
            content_id=UUID(int=number),
            content_version_id=UUID(int=number + 1000),
            source_key="rss_test",
            title="受控材料",
            body=None,
            first_seen_at=NOW,
            first_seen_basis="published",
            matched_keywords=frozenset(),
            editorial_scope="composite" if number == 3 else "unknown" if number == 4 else "single",
        )
        for number in range(1, 6)
    )
    monkeypatch.setattr(
        module,
        "load_event_input_source_modes_in_transaction",
        lambda *a, **k: {
            item.content_version_id: "isolated" if index == 0 else "legacy"
            for index, item in enumerate(inputs)
        },
    )
    session = SimpleNamespace(
        in_transaction=lambda: True,
        scalars=lambda _: [SimpleNamespace(topic_id=topic, content_id=UUID(int=2))],
    )
    exempt = module.load_selection_grouping_exempt_ids_in_transaction(
        session, owner_id=owner, inputs=inputs, now=NOW
    )
    assert exempt == frozenset(UUID(int=number) for number in (1, 2, 3))
    # Unknown scope and an ordinary in-scope item still require grouping.
    assert UUID(int=4) not in exempt and UUID(int=5) not in exempt


def test_session_factory_keeps_the_explicit_process_settings_for_every_outlet():
    from sqlalchemy import create_engine

    from db.session import create_session_factory

    settings = Settings(
        environment="test",
        database_url="postgresql+psycopg://test:test@127.0.0.1:5432/hotkey_test_selection",
        events_cluster_enabled=True,
    )
    engine = create_engine(settings.database_url.get_secret_value())
    try:
        sessions = create_session_factory(engine, settings=settings)
        with sessions() as first, sessions() as second:
            assert first.info["settings"] is settings and second.info["settings"] is settings
            assert first.info is not second.info
    finally:
        engine.dispose()
