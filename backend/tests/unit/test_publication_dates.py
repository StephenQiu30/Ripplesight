"""Unknown publication dates retain raw reading while blocking derived selection."""

from datetime import UTC, datetime
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
from publication.projection import derive_projection
from publication.reading import public_item
from publication.schemas import SourcePolicyView
from tests.unit.test_editorial_rules import material
from tests.unit.test_publication_groups import member

NOW = datetime(2026, 10, 2, tzinfo=UTC)


@pytest.mark.parametrize("manual", [False, True])
def test_undated_selected_result_keeps_raw_reading_and_requires_a_new_dated_input(manual):
    source = EditorialSourceView(
        source_key="rss_test",
        revision=1,
        tier="T1",
        source_kind="rss",
        name="发布者",
        first_party=False,
        owner_entity_id=None,
        tags=[],
        enabled=True,
    )
    original = material(excerpt="原始来源摘要")
    run = EditorialRunView(
        id=uuid4(),
        job_id=uuid4(),
        content_id=original.content_id,
        content_version_id=original.content_version_id,
        source_key=source.source_key,
        source_revision=1,
        prompt_version="controlled",
        manual_version=int(manual),
        status="complete",
        failure_code=None,
        created_at=NOW,
        updated_at=NOW,
        result=EditorialResultView(
            relevance="pass",
            selected=True,
            score=95,
            manual=manual,
            writing=EditorialWritingView(
                title_zh="模型发布",
                summary_zh="公开使用方式",
                kind="manual" if manual else "understand",
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
        timeline_at=NOW,
        first_received_at=NOW,
        backfill=None,
    )
    policy = SourcePolicyView(
        source_key=source.source_key,
        revision=1,
        participation_mode="editorial",
        site_fulltext=False,
        syndicate_fulltext=False,
        indexable=False,
        release_delay_seconds=0,
        license_name="受控许可",
        license_url=None,
        updated_at=NOW,
    )
    projection = derive_projection(snapshot, policy, now=NOW)
    assert projection.eligible and projection.visibility == "public"
    assert not projection.selected and projection.visible_after is None
    assert projection.published_at is None and projection.discovered_at == NOW
    assert public_item(projection).published_at is None
    raw = derive_projection(snapshot.model_copy(update={"run": None}), policy, now=NOW)
    assert raw.eligible and raw.summary == "原始来源摘要" and not raw.selected
    dated = derive_projection(
        snapshot.model_copy(update={"material": original.model_copy(update={"published_at": NOW})}),
        policy,
        now=NOW,
        previous=projection,
    )
    assert dated.selected and dated.visible_after == NOW


@pytest.mark.parametrize("missing", ["member", "hidden_member", "narrative", "analysis_input"])
def test_public_story_requires_dates_for_all_members_and_complete_narrative_inputs(
    monkeypatch, missing
):
    import publication.stories as module
    from publication.reading import PublicationReadingService

    event, fact, extra = uuid4(), uuid4(), uuid4()
    displayed = member(at=NOW, event=event, fact=fact).projection.model_copy(
        update={"observation_id": uuid4(), "published_at": None if missing == "member" else NOW}
    )
    hidden = member(at=NOW).projection.model_copy(
        update={
            "observation_id": uuid4(),
            "published_at": None if missing == "hidden_member" else NOW,
        }
    )
    sources = {
        displayed.observation_id: displayed.source_key,
        hidden.observation_id: hidden.source_key,
        extra: displayed.source_key,
    }
    undated_inputs = {extra} if missing in {"narrative", "analysis_input"} else set()
    story = SimpleNamespace(
        event_id=event,
        revision=1,
        title="固定故事",
        summary="全部输入摘要",
        latest_progress=None,
        phase="active",
        first_seen_at=NOW,
        heat=None,
        attention=None,
        narrative_input_observation_ids=(displayed.observation_id, hidden.observation_id)
        + ((extra,) if missing == "narrative" else ()),
        members=tuple(
            SimpleNamespace(
                content_id=p.content_id,
                content_version_id=p.content_version_id,
                observation_id=p.observation_id,
                source_key=p.source_key,
                input_observation_ids=(p.observation_id,)
                + ((extra,) if missing == "analysis_input" else ()),
            )
            for p in (displayed, hidden)
        ),
    )
    monkeypatch.setattr(
        module, "load_publication_stories_in_transaction", lambda *a, **k: {event: story}
    )
    monkeypatch.setattr(
        module,
        "load_observation_context_in_transaction",
        lambda *a, observation_id, **k: SimpleNamespace(
            source_key=sources[observation_id],
            published_at=None if observation_id in undated_inputs else NOW,
        ),
    )
    reader = PublicationReadingService(
        SimpleNamespace(
            scalars=lambda _: [],
            get=lambda *a: SimpleNamespace(configuration={"participation_mode": "editorial"}),
        )
    )
    values = {p.content_id: (p, None) for p in (displayed, hidden)}
    monkeypatch.setattr(reader, "_live", lambda **_: values)
    assert not module.public_stories_in_transaction(
        reader, owner_id=uuid4(), event_ids=(event,), now=NOW
    )
    undated_inputs.clear()
    for identity, (p, _) in values.items():
        values[identity] = (p.model_copy(update={"published_at": NOW}), None)
    result = module.public_stories_in_transaction(
        reader, owner_id=uuid4(), event_ids=(event,), now=NOW
    )
    assert len(result) == 1 and len(result[0].reports) == 1
