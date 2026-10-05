"""Translation selection is independent of the public trusted-date requirement."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from analysis.editorial_schemas import (
    EditorialPublicationInputView,
    EditorialResultView,
    EditorialRunView,
    EditorialSourceView,
    EditorialWritingView,
)
from analysis.editorial_selection import EditorialSelectionCandidate, decide_editorial_selection
from analysis.translation_services import _grant
from publication.projection import derive_projection
from publication.reading import full_text_grant_in_transaction
from publication.schemas import SourcePolicyView
from tests.unit.test_editorial_rules import material

NOW = datetime(2026, 10, 5, tzinfo=UTC)


def translation_input(*, dated=False, selected=True, relevance="pass", tier="T1", raw=False):
    original = material(body_complete=True, published_at=NOW if dated else None)
    source = EditorialSourceView(
        source_key=original.source_key,
        revision=1,
        tier=tier,
        source_kind="rss",
        name="发布者",
        first_party=False,
        owner_entity_id=None,
        tags=[],
        enabled=True,
    )
    run = EditorialRunView(
        id=uuid4(),
        job_id=uuid4(),
        content_id=original.content_id,
        content_version_id=original.content_version_id,
        source_key=source.source_key,
        source_revision=1,
        prompt_version="controlled",
        manual_version=0,
        status="complete",
        failure_code=None,
        created_at=NOW,
        updated_at=NOW,
        result=EditorialResultView(
            relevance=relevance,
            selected=selected,
            writing=EditorialWritingView(
                title_zh="模型发布",
                summary_zh="固定材料摘要",
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
        run=None if raw else run,
        source=source,
        material=original,
        timeline_at=NOW,
        first_received_at=NOW,
        backfill=None,
    )
    policy = SourcePolicyView(
        source_key=source.source_key,
        revision=1,
        participation_mode="editorial",
        site_fulltext=True,
        syndicate_fulltext=False,
        indexable=False,
        release_delay_seconds=0,
        license_name="受控全文许可",
        license_url=None,
        updated_at=NOW,
    )
    selection = decide_editorial_selection(
        [
            EditorialSelectionCandidate(
                snapshot,
                None,
                selected and relevance == "pass" and tier != "T4" and not raw,
                grouping_enabled=False,
            )
        ]
    )[original.content_id]
    return snapshot, derive_projection(
        snapshot,
        policy,
        now=NOW,
        selection=selection,
    )


def grant_context(monkeypatch, snapshot, projection):
    import publication.reading as reading

    session = SimpleNamespace(in_transaction=lambda: True, get=lambda *_args: object())
    record = SimpleNamespace(
        owner_id=uuid4(),
        content_id=projection.content_id,
        content_version_id=projection.content_version_id,
        policy_revision=projection.policy_revision,
    )
    body_reads = []

    def read_body(*_args, **_kwargs):
        body_reads.append(projection.content_id)
        return snapshot.material.body, "text", "a" * 64, []

    monkeypatch.setattr(
        reading.PublicationReadingService,
        "_live",
        lambda *_args, **_kwargs: {projection.content_id: (projection, snapshot)},
    )
    monkeypatch.setattr(reading, "_fixed_body_in_transaction", read_body)
    return session, record, body_reads


def test_undated_editorial_selection_can_translate_without_becoming_public_selected(monkeypatch):
    snapshot, projection = translation_input()
    assert projection.eligible and not projection.selected and projection.visible_after is None
    session, record, body_reads = grant_context(monkeypatch, snapshot, projection)
    grant = _grant(session, record, NOW)
    assert grant.granted and grant.body == snapshot.material.body and grant.reference is not None
    assert body_reads == [projection.content_id]
    # Other grant consumers retain the public selection/release requirement.
    assert not full_text_grant_in_transaction(
        session,
        owner_id=record.owner_id,
        content_id=record.content_id,
        content_version_id=record.content_version_id,
        policy_revision=record.policy_revision,
        now=NOW,
    ).granted
    assert body_reads == [projection.content_id]
    assert not projection.selected and projection.published_at is None


@pytest.mark.parametrize(
    "blocked",
    [
        "not_selected",
        "raw",
        "unknown_relevance",
        "excluded_tier",
        "summary_only",
        "withdrawn",
        "no_fulltext",
        "new_version",
        "new_policy",
        "missing_input",
        "pending_release",
    ],
)
def test_undated_translation_still_requires_current_selection_and_fulltext_grant(
    monkeypatch, blocked
):
    snapshot, projection = translation_input(
        selected=blocked != "not_selected",
        raw=blocked == "raw",
        relevance="unknown" if blocked == "unknown_relevance" else "pass",
        tier="EXCLUDE_MP" if blocked == "excluded_tier" else "T1",
    )
    if blocked in {"summary_only", "withdrawn"}:
        projection = projection.model_copy(
            update={"visibility": "summary-only" if blocked == "summary_only" else "withdrawn"}
        )
    elif blocked == "no_fulltext":
        projection = projection.model_copy(update={"body_mode": "summary"})
    elif blocked == "pending_release":
        projection = projection.model_copy(update={"visible_after": NOW + timedelta(seconds=180)})
    session, record, body_reads = grant_context(monkeypatch, snapshot, projection)
    if blocked == "new_version":
        record.content_version_id = uuid4()
    elif blocked == "new_policy":
        record.policy_revision += 1
    elif blocked == "missing_input":
        from publication.reading import PublicationReadingService

        monkeypatch.setattr(PublicationReadingService, "_live", lambda *_args, **_kwargs: {})
    grant = _grant(session, record, NOW)
    assert not grant.granted and grant.body is None and grant.reference is None
    assert not body_reads


@pytest.mark.parametrize("released", [False, True])
def test_dated_translation_preserves_the_existing_release_gate(monkeypatch, released):
    snapshot, projection = translation_input(dated=True)
    projection = projection.model_copy(update={"visible_after": NOW + timedelta(seconds=180)})
    session, record, body_reads = grant_context(monkeypatch, snapshot, projection)
    grant = _grant(session, record, NOW + timedelta(seconds=181) if released else NOW)
    assert grant.granted is released
    assert bool(body_reads) is released
