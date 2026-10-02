from datetime import UTC, datetime, timedelta

from monitors.codex_schemas import Estimate, Proposition, Recognition, ResetEventView
from monitors.codex_services import presentation_status, quoted_in_post, validated_propositions


def test_quotes_are_checked_independently_of_model_relevance() -> None:
    assert quoted_in_post("Reset…everyone", "Reset limits for everyone! https://x.com/1")
    assert not quoted_in_post("Reset all propagated", "We'll reset tomorrow")
    rec = Recognition(
        relevant=True,
        needs_review=False,
        propositions=(
            Proposition(
                kind="direct_reset", action="confirm", real=True, excerpt="Reset all propagated"
            ),
        ),
    )
    accepted, held = validated_propositions(rec, "We'll reset tomorrow")
    assert not accepted and len(held) == 1


def test_review_and_unstated_multiple_rounds_are_held_or_reduced() -> None:
    p = Proposition(
        kind="direct_reset", action="announce", real=True, count=2, excerpt="More resets coming"
    )
    rec = Recognition(relevant=True, needs_review=False, propositions=(p,))
    accepted, held = validated_propositions(rec, p.excerpt)
    assert accepted[0].count == 1 and not held
    accepted, held = validated_propositions(
        rec.model_copy(update={"needs_review": True}), p.excerpt
    )
    assert not accepted and held


def test_contradictory_irrelevant_recognition_cannot_confirm_public_facts() -> None:
    proposition = Proposition(kind="direct_reset", action="confirm", real=True, excerpt="All done")
    rec = Recognition(relevant=False, needs_review=False, propositions=(proposition,))
    accepted, held = validated_propositions(rec, "All done")
    assert not accepted and held


def test_expiration_never_confirms_an_event() -> None:
    now = datetime(2026, 9, 26, 1, tzinfo=UTC)
    e = ResetEventView(
        id="reset-1",
        kind="direct_reset",
        status="announced",
        revision=1,
        created_at=now,
        updated_at=now,
        estimate=Estimate(
            starts_at=now,
            ends_at=now + timedelta(hours=1),
            basis="history",
            label="预计",
            reason="测试",
        ),
    )
    assert presentation_status(e, now) == "announced"
    assert presentation_status(e.model_copy(update={"in_progress": True}), now) == "in_progress"
    assert presentation_status(e, now + timedelta(hours=1)) == "expired_unconfirmed"
    assert presentation_status(e, now + timedelta(hours=7)) == "likely_completed"
    assert e.status == "announced"
